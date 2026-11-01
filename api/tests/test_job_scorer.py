from types import SimpleNamespace

from app.services.job_parser import parse_job_description
from app.services.job_scorer import Profile, score_job


def test_score_job_returns_high_score_for_profile_match() -> None:
    raw_text = """
    Senior Backend Engineer
    Company: Lantern Cloud
    Location: Remote
    Build FastAPI services with PostgreSQL, SQLAlchemy, and TypeScript frontends.
    """
    job = parse_job_description(raw_text)
    profile = Profile(
        preferred_roles=["backend", "full-stack"],
        tech_stack={"python", "fastapi", "postgresql", "typescript", "react"},
        remote_only=True,
        allowed_seniority={"senior"},
    )

    score, reasons = score_job(job, profile)

    assert score >= 70
    assert reasons


def test_score_job_returns_lower_score_for_mismatch() -> None:
    raw_text = """
    iOS Engineer
    Company: Appverse
    Location: On-site
    Design Swift UI and work with Apple ecosystems.
    """
    job = parse_job_description(raw_text)
    profile = Profile(
        preferred_roles=["backend", "full-stack"],
        tech_stack={"python", "fastapi", "postgresql", "react"},
        remote_only=True,
    )

    score, _ = score_job(job, profile)
    assert score < 50


def test_stage_one_excludes_titles_outside_target_roles() -> None:
    job = SimpleNamespace(
        title="Frontend Engineer",
        description="Build React interfaces",
        location="Remote",
        skills=["react"],
    )

    score, reasons = score_job(job, Profile())

    assert score == 0
    assert "excluded: title is not full-stack or backend" in reasons


def test_stage_one_excludes_seniority_unless_profile_allows_it() -> None:
    job = SimpleNamespace(
        title="Staff Backend Engineer",
        description="Build APIs",
        location="Remote",
        skills=["python"],
    )

    rejected_score, rejected_reasons = score_job(job, Profile())
    allowed_score, _ = score_job(job, Profile(allowed_seniority={"staff"}))

    assert rejected_score == 0
    assert any("seniority not allowed" in reason for reason in rejected_reasons)
    assert allowed_score > 0


def test_stage_one_checks_country_timezone_and_work_authorization() -> None:
    job = SimpleNamespace(
        title="Backend Engineer",
        description=(
            "Only applicants located in the United States. "
            "Must overlap with EST business hours. "
            "Must be authorized to work in the United States."
        ),
        location="Remote",
        skills=["python"],
    )

    score, reasons = score_job(
        job,
        Profile(
            country="Kenya",
            timezones={"EAT"},
            work_authorizations={"Kenya"},
        ),
    )

    assert score == 0
    assert "excluded: country restriction does not include your country" in reasons
    assert "excluded: timezone restriction does not match your timezones" in reasons
    assert "excluded: work-authorization requirement is not in your profile" in reasons


def test_stage_one_detects_country_work_authorization_requirement() -> None:
    job = SimpleNamespace(
        title="Backend Engineer",
        description="US work authorization required.",
        location="Remote",
        skills=[],
    )

    score, reasons = score_job(job, Profile(work_authorizations={"Kenya"}))

    assert score == 0
    assert "excluded: work-authorization requirement is not in your profile" in reasons


def test_stage_one_keeps_region_requirements_matching_profile() -> None:
    job = SimpleNamespace(
        title="Backend Engineer",
        description=(
            "Only applicants located in Kenya. "
            "Must overlap with EAT. "
            "Must be authorized to work in Kenya."
        ),
        location="Remote",
        skills=["python"],
    )

    score, reasons = score_job(
        job,
        Profile(
            country="Kenya",
            timezones={"EAT"},
            work_authorizations={"Kenya"},
        ),
    )

    assert score > 0
    assert all(not reason.startswith("excluded:") for reason in reasons)
