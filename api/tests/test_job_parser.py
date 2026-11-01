from app.services.job_parser import parse_job_description


def test_parse_job_description_extracts_details() -> None:
    raw_text = """
    Title: Senior Full-Stack Engineer
    Company: Northstar Labs
    Location: Remote
    We build Python FastAPI backends and TypeScript React apps relying on PostgreSQL.
    """

    job = parse_job_description(raw_text, source="greenhouse", url="https://example.com/jobs/42")

    assert "Senior Full-Stack Engineer" in job.title
    assert job.company == "Northstar Labs"
    assert job.location == "Remote"
    assert job.remote is True
    assert "python" in job.skills
    assert "postgresql" in job.skills
