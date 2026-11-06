"""Tech role families used to decide which job titles are relevant.

A user picks families (for example "backend" or "devops") instead of typing job
titles. Every family has a title pattern for matching jobs and a few search phrases
for finding more company boards. Nothing here calls the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleFamily:
    key: str
    label: str
    pattern: re.Pattern[str]
    search_phrases: tuple[str, ...]


def _compile(*alternatives: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{item})" for item in alternatives), re.IGNORECASE)


_LANGUAGES = (
    r"python|java|javascript|typescript|ruby|php|golang|rust|scala|kotlin|swift|c\+\+|c#|\.net|"
    r"node(?:\.?js)?|elixir|salesforce|wordpress|shopify|sap|laravel|django|rails|react|angular|vue"
)
_AI_TERM = (
    r"(?:ai|ml|machine learning|deep learning|nlp|llm|computer vision|generative ai|genai|"
    r"data science)"
)
_PERSON = r"(?:engineer|developer|scientist|researcher|architect|specialist|lead)"

ROLE_FAMILIES: tuple[RoleFamily, ...] = (
    RoleFamily(
        "backend", "Backend",
        _compile(r"\bback[\s-]*end\b", r"\bserver[\s-]*side\b", r"\bapi (?:engineer|developer)\b"),
        ("backend engineer", "backend developer"),
    ),
    RoleFamily(
        "frontend", "Frontend",
        _compile(
            r"\bfront[\s-]*end\b", r"\bui (?:engineer|developer)\b", r"\bweb developer\b",
            r"\b(?:react|angular|vue|javascript|typescript) (?:engineer|developer)\b",
        ),
        ("frontend engineer", "frontend developer"),
    ),
    RoleFamily(
        "full-stack", "Full-stack",
        _compile(r"\bfull[\s-]*stack\b"),
        ("full stack engineer", "full stack developer"),
    ),
    RoleFamily(
        "software-engineer", "Software engineer (general)",
        _compile(
            r"\bsoftware\b[\w\s,/&()-]{0,25}?\b(?:engineer|developer)\b",
            r"\bswe\b", r"\bprogrammer\b", r"\bapplication (?:engineer|developer)\b",
            rf"\b(?:{_LANGUAGES})\s+(?:engineer|developer)\b",
        ),
        ("software engineer", "software developer"),
    ),
    RoleFamily(
        "mobile", "Mobile",
        _compile(
            r"\bmobile\s+(?:\w+\s+)?(?:engineer|developer|architect)\b",
            r"\bios\s+(?:\w+\s+)?(?:engineer|developer)\b",
            r"\bandroid\s+(?:\w+\s+)?(?:engineer|developer)\b",
            r"\breact native\b", r"\bflutter\b",
        ),
        ("mobile engineer", "ios developer"),
    ),
    RoleFamily(
        "devops", "DevOps, SRE and cloud",
        _compile(
            r"\bdevops\b", r"\bdevsecops\b", r"\bsre\b", r"\bsite reliability\b",
            r"\bplatform engineer", r"\binfrastructure engineer", r"\bcloud (?:engineer|architect|developer)\b",
            r"\bsystems? (?:engineer|administrator|admin)\b", r"\bsysadmin\b",
            r"\brelease engineer", r"\bbuild engineer", r"\bnetwork engineer",
        ),
        ("devops engineer", "site reliability engineer"),
    ),
    RoleFamily(
        "data", "Data and analytics",
        _compile(
            r"\bdata (?:engineer|analyst|scientist|architect|analytics|platform)", r"\banalytics engineer",
            r"\bbi (?:developer|analyst|engineer)\b", r"\bbusiness intelligence\b",
            r"\bdatabase (?:administrator|engineer|developer)\b", r"\bdba\b",
            r"\betl (?:developer|engineer)\b", r"\bdata warehouse\b",
        ),
        ("data engineer", "data analyst"),
    ),
    RoleFamily(
        "ml-ai", "Machine learning and AI",
        _compile(
            rf"\b{_AI_TERM}\b[\w\s/,&-]{{0,20}}?\b{_PERSON}\b",
            rf"\b(?:engineer|scientist|researcher)\b[\w\s/,&-]{{0,15}}?\b{_AI_TERM}\b",
            r"\bapplied scientist\b", r"\bresearch (?:scientist|engineer)\b", r"\bmlops\b",
            r"\bprompt engineer",
        ),
        ("machine learning engineer", "ai engineer"),
    ),
    RoleFamily(
        "qa", "QA and testing",
        _compile(
            r"\bqa\b", r"\bquality assurance\b", r"\bsdet\b", r"\btest (?:engineer|automation|analyst)",
            r"\bsoftware tester\b", r"\bautomation (?:engineer|tester)\b", r"\bquality engineer",
        ),
        ("qa engineer", "sdet"),
    ),
    RoleFamily(
        "security", "Security",
        _compile(
            r"\bsecurity (?:engineer|analyst|architect|researcher|specialist|consultant|operations)",
            r"\bappsec\b", r"\binfosec\b", r"\bcyber\s*security\b", r"\bpenetration test",
            r"\bpentest", r"\bsoc analyst\b", r"\bthreat (?:intelligence|hunter|analyst)",
        ),
        ("security engineer", "application security"),
    ),
    RoleFamily(
        "design", "Product design and UX",
        _compile(
            r"\bux\b", r"\bui/ux\b", r"\bproduct designer\b", r"\bui designer\b",
            r"\buser experience\b", r"\buser interface\b", r"\binteraction designer\b",
            r"\bdesign systems?\b", r"\bvisual designer\b", r"\bweb designer\b",
        ),
        ("product designer", "ux designer"),
    ),
    RoleFamily(
        "product", "Product and project management",
        _compile(
            r"\bproduct (?:manager|owner|lead|analyst)\b", r"\btechnical product\b",
            r"\bprogram manager\b", r"\bproject manager\b", r"\bscrum master\b",
            r"\bdelivery manager\b", r"\bagile coach\b", r"\bbusiness analyst\b",
        ),
        ("product manager", "technical program manager"),
    ),
    RoleFamily(
        "engineering-management", "Engineering management",
        _compile(
            r"\bengineering manager\b", r"\bhead of engineering\b", r"\bvp (?:of )?engineering\b",
            r"\bdirector of engineering\b", r"\bcto\b", r"\bchief technology officer\b",
            r"\btech(?:nical)? lead\b",
        ),
        ("engineering manager", "technical lead"),
    ),
    RoleFamily(
        "support", "Technical support and solutions",
        _compile(
            r"\b(?:technical|customer|it|application|product|desktop) support\b",
            r"\bsupport engineer", r"\bsolutions? (?:engineer|architect|consultant)",
            r"\bsales engineer", r"\bcustomer success engineer", r"\btechnical account manager\b",
            r"\b(?:implementation|integration) (?:engineer|specialist|consultant)",
            r"\bit (?:administrator|specialist|technician)\b", r"\bhelp ?desk\b",
        ),
        ("support engineer", "solutions engineer"),
    ),
    RoleFamily(
        "devrel-docs", "Developer relations and technical writing",
        _compile(
            r"\bdeveloper (?:advocate|relations|evangelist|experience|educator)\b", r"\bdevrel\b",
            r"\btechnical writer\b", r"\bdocumentation (?:engineer|writer)\b",
        ),
        ("developer advocate", "technical writer"),
    ),
    RoleFamily(
        "embedded", "Embedded and hardware",
        _compile(
            r"\bembedded\b", r"\bfirmware\b", r"\bfpga\b", r"\bhardware engineer\b",
            r"\brobotics\b", r"\biot (?:engineer|developer)", r"\bverification engineer\b",
        ),
        ("embedded engineer", "firmware engineer"),
    ),
    RoleFamily(
        "game", "Game development",
        _compile(
            r"\bgame (?:developer|engineer|designer|programmer)\b", r"\bgameplay\b",
            r"\bgraphics (?:engineer|programmer)\b", r"\bunity (?:developer|engineer)\b",
            r"\bunreal\b",
        ),
        ("game developer", "gameplay engineer"),
    ),
    RoleFamily(
        "web3", "Blockchain and web3",
        _compile(
            r"\bblockchain\b", r"\bweb3\b", r"\bsmart contract\b", r"\bsolidity\b",
            r"\bcrypto (?:engineer|developer)\b", r"\bprotocol engineer\b",
        ),
        ("blockchain engineer", "smart contract developer"),
    ),
)

FAMILIES_BY_KEY: dict[str, RoleFamily] = {family.key: family for family in ROLE_FAMILIES}
ALL_FAMILY_KEYS: tuple[str, ...] = tuple(FAMILIES_BY_KEY)


def split_role_values(values: list[str] | None) -> tuple[list[str], list[str]]:
    """Separate known family keys from free text kept from older profiles."""
    keys: list[str] = []
    custom: list[str] = []
    for value in values or []:
        normalized = value.strip().casefold()
        if not normalized:
            continue
        if normalized in FAMILIES_BY_KEY:
            if normalized not in keys:
                keys.append(normalized)
        elif normalized not in custom:
            custom.append(normalized)
    return keys, custom


def matching_families(title: str) -> list[str]:
    return [family.key for family in ROLE_FAMILIES if family.pattern.search(title or "")]


def is_tech_title(title: str) -> bool:
    """True when the title belongs to any tech role family."""
    return any(family.pattern.search(title or "") for family in ROLE_FAMILIES)


def matches_roles(
    title: str, role_values: list[str] | None, custom_keywords: list[str] | None = None
) -> bool:
    """Does the title match the user's selection?

    With no selection at all, every tech family counts. Free text from older
    profiles and ``custom_keywords`` match as plain, case-insensitive substrings.
    """
    keys, free_text = split_role_values(role_values)
    keywords = free_text + [item.strip().casefold() for item in custom_keywords or [] if item.strip()]
    lowered = (title or "").casefold()
    if any(keyword in lowered for keyword in keywords):
        return True
    if keys:
        return any(FAMILIES_BY_KEY[key].pattern.search(title or "") for key in keys)
    return False if keywords else is_tech_title(title)


def search_phrases_for(role_values: list[str] | None) -> list[str]:
    keys, _custom = split_role_values(role_values)
    chosen = keys or list(ALL_FAMILY_KEYS)
    phrases: list[str] = []
    for key in chosen:
        for phrase in FAMILIES_BY_KEY[key].search_phrases:
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases


def catalog() -> list[dict[str, str]]:
    return [{"key": family.key, "label": family.label} for family in ROLE_FAMILIES]
