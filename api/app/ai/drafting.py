"""Cover-letter and answer drafts: template-based by default, AI-assisted when available.

Everything written here must come from facts the user put in their profile. The
template path only uses profile facts; the AI path is instructed the same way and
its output is checked by a second call that flags unsupported claims.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.client import AIUnavailableError, complete, complete_json
from app.services.cv import redact_contact_details

logger = logging.getLogger("openhunt.drafting")

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
MAX_DESCRIPTION_CHARS = 3500


def strip_html(value: str | None) -> str:
    """Turn a (possibly HTML) job description into plain text."""
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", text)
    text = _TAG_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return _BLANK_LINES_RE.sub("\n\n", text).strip()


@dataclass
class DraftProfile:
    full_name: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = field(default_factory=list)
    target_roles: list[str] = field(default_factory=list)
    projects: list[dict[str, str]] = field(default_factory=list)
    cv_excerpt: str = ""

    def facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {
            "full_name": self.full_name,
            "headline": self.headline,
            "summary": self.summary,
            "skills": self.skills,
            "target_roles": self.target_roles,
            "projects": self.projects,
        }
        if self.cv_excerpt:
            # Emails and phone numbers never leave the server.
            facts["cv_excerpt"] = redact_contact_details(self.cv_excerpt)[:4000]
        return facts


@dataclass
class Draft:
    cover_letter: str
    answers: dict[str, str]
    generated_by: str
    warnings: list[str] = field(default_factory=list)


def _matched_skills(profile: DraftProfile, text: str) -> list[str]:
    lowered = text.casefold()
    return [
        skill
        for skill in profile.skills
        if skill.strip() and re.search(rf"(?<!\w){re.escape(skill.casefold())}(?!\w)", lowered)
    ]


def _project_line(project: dict[str, str]) -> str:
    name = project.get("name", "").strip()
    description = project.get("description", "").strip()
    url = project.get("url", "").strip()
    parts = [name]
    if description:
        parts.append(f"- {description}")
    line = " ".join(part for part in parts if part)
    return f"{line} ({url})" if url and line else line


def profile_warnings(profile: DraftProfile) -> list[str]:
    warnings: list[str] = []
    if not profile.full_name:
        warnings.append("Add your full name in Profile so the letter can be signed.")
    if not (profile.summary or profile.headline):
        warnings.append("Add a short summary in Profile to make the letter more specific.")
    if not profile.projects:
        warnings.append("Add one or two projects in Profile so the letter can point to real work.")
    return warnings


def template_draft(
    title: str, company: str | None, description: str | None, profile: DraftProfile
) -> Draft:
    plain = strip_html(description)
    matched = _matched_skills(profile, f"{title}\n{plain}")
    at_company = f" at {company}" if company else ""

    paragraphs = [f"Dear Hiring Team{at_company}," if company else "Dear Hiring Team,"]

    intro = f"I am writing to apply for the {title} role{at_company}."
    about = profile.summary or profile.headline
    if about:
        intro += f" {about.strip()}"
    paragraphs.append(intro)

    if matched:
        paragraphs.append(
            "The role mentions "
            + ", ".join(matched[:6])
            + ", which are part of the stack I work with."
        )

    project_lines = [_project_line(project) for project in profile.projects[:2]]
    project_lines = [line for line in project_lines if line]
    if project_lines:
        paragraphs.append("Work I would point to: " + "; ".join(project_lines) + ".")

    paragraphs.append(
        "I would welcome the chance to talk about how I can contribute to your team. "
        "Thank you for your time and consideration."
    )
    signature = "Best regards," + (f"\n{profile.full_name}" if profile.full_name else "")
    paragraphs.append(signature)

    answers: dict[str, str] = {}
    if profile.target_roles or about:
        focus = ", ".join(profile.target_roles) if profile.target_roles else None
        sentence = f"I am drawn to the {title} role{at_company}"
        if focus:
            sentence += f" because it fits my focus on {focus} work"
        answers["why_this_role"] = sentence + "."
    experience: list[str] = []
    if matched:
        experience.append("Relevant skills: " + ", ".join(matched) + ".")
    if project_lines:
        experience.append("Projects: " + "; ".join(project_lines) + ".")
    if experience:
        answers["relevant_experience"] = " ".join(experience)

    return Draft(
        cover_letter="\n\n".join(paragraphs),
        answers=answers,
        generated_by="template",
        warnings=profile_warnings(profile),
    )


class _Verification(BaseModel):
    unsupported_claims: list[str] = Field(default_factory=list)


_SYSTEM_PROMPT = (
    "You write short, honest cover letters for job applicants. Use ONLY the facts in the "
    "APPLICANT FACTS JSON. Never invent employers, years of experience, degrees, "
    "numbers, or skills that are not listed. If a fact is missing, leave it out. "
    "Write 150-230 words in plain text with no markdown, no placeholders in brackets, "
    "and no subject line. Start with a greeting and end with a sign-off using the "
    "applicant's name when it is provided."
)


def ai_draft(
    db: Session,
    title: str,
    company: str | None,
    description: str | None,
    profile: DraftProfile,
) -> Draft | None:
    """Return an AI-written draft, or None when no provider can answer."""
    plain = strip_html(description)[:MAX_DESCRIPTION_CHARS]
    payload = json.dumps(
        {
            "APPLICANT FACTS": profile.facts(),
            "JOB": {"title": title, "company": company, "description": plain},
        },
        ensure_ascii=False,
    )
    try:
        result = complete(
            db,
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ],
            max_tokens=700,
            temperature=0.4,
            # The prompt can contain CV text, so only no-training providers may see it.
            sensitive=True,
        )
    except AIUnavailableError as error:
        logger.info("AI drafting unavailable, using the template: %s", error)
        return None

    warnings = profile_warnings(profile)
    try:
        check = complete_json(
            db,
            [
                {
                    "role": "system",
                    "content": (
                        "You check cover letters for unsupported claims. Reply with only a JSON "
                        'object {"unsupported_claims": [strings]} listing any statement in the '
                        "LETTER that is not supported by the APPLICANT FACTS or the JOB. "
                        "Use an empty list when everything is supported."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"APPLICANT FACTS": profile.facts(), "JOB": title, "LETTER": result.text},
                        ensure_ascii=False,
                    ),
                },
            ],
            _Verification,
            sensitive=True,
        )
        for claim in check.unsupported_claims[:5]:
            warnings.append(f"Check this claim, it is not in your profile: {claim}")
    except AIUnavailableError:
        warnings.append("The automatic fact check could not run. Read the letter carefully.")

    return Draft(
        cover_letter=result.text,
        answers={},
        generated_by=f"{result.provider}:{result.model}",
        warnings=warnings,
    )


def generate_draft(
    db: Session,
    title: str,
    company: str | None,
    description: str | None,
    profile: DraftProfile,
    *,
    use_ai: bool = True,
) -> Draft:
    base = template_draft(title, company, description, profile)
    if not use_ai:
        return base
    written = ai_draft(db, title, company, description, profile)
    if written is None:
        return base
    # Keep the template's fact-only answers; they never contain invented claims.
    written.answers = base.answers
    return written
