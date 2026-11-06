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
    assert "excluded: title does not match your selected role types" in reasons


def test_every_tech_role_counts_when_no_role_types_are_selected() -> None:
    frontend = SimpleNamespace(title="Frontend Engineer", description="React", location="Remote", skills=[])
    devops = SimpleNamespace(title="DevOps Engineer", description="Kubernetes", location="Remote", skills=[])
    sales = SimpleNamespace(title="Account Executive", description="Sell things", location="Remote", skills=[])

    everything = Profile(preferred_roles=[])

    assert score_job(frontend, everything)[0] > 0
    assert score_job(devops, everything)[0] > 0
    assert score_job(sales, everything)[0] == 0


def test_custom_title_keywords_extend_the_match() -> None:
    job = SimpleNamespace(title="Technical Recruiter", description="Hire engineers", location="Remote", skills=[])

    assert score_job(job, Profile(preferred_roles=[]))[0] == 0
    assert score_job(job, Profile(preferred_roles=[], custom_title_keywords=["recruiter"]))[0] > 0


def test_skill_mentions_in_the_description_raise_the_score() -> None:
    plain = SimpleNamespace(title="Backend Engineer", description="Build services", location="Remote", skills=[])
    rich = SimpleNamespace(title="Backend Engineer", description="Build services in Rust and Kafka", location="Remote", skills=[])
    profile = Profile(tech_stack={"rust", "kafka"})

    assert score_job(rich, profile)[0] > score_job(plain, profile)[0]


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


def test_scoring_accepts_the_dictionaries_the_dashboard_builds() -> None:
    """Regression: dict jobs used to look title-less, so every dashboard job scored 0."""
    job = {
        "title": "Backend Engineer",
        "description": "Build FastAPI services",
        "location_text": "Remote",
        "seniority": None,
        "skills": ["python"],
    }

    score, reasons = score_job(job, Profile(tech_stack={"python", "fastapi"}))

    assert score >= 60
    assert "role match" in reasons
