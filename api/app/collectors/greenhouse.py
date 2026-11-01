from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.collectors.base import (
    CollectorError,
    NormalizedJob,
    PublicCollector,
    fetch_json,
    infer_remote_scope,
    parse_datetime,
)
from app.models.company import Company


class GreenhouseCollector(PublicCollector):
    ats_type = "greenhouse"
    endpoint = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

    def fetch(self, company: Company) -> list[dict[str, Any]]:
        payload = fetch_json(self.endpoint.format(slug=quote(company.ats_slug, safe="")))
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise CollectorError("Greenhouse response must contain a jobs array")
        if not all(isinstance(job, dict) for job in payload["jobs"]):
            raise CollectorError("Greenhouse jobs array contains a malformed item")
        return payload["jobs"]

    def normalize(self, company: Company, payload: dict[str, Any]) -> NormalizedJob:
        job_id = payload.get("id")
        title = payload.get("title")
        url = payload.get("absolute_url")
        if job_id is None or not isinstance(title, str) or not isinstance(url, str):
            raise CollectorError("Greenhouse job is missing id, title, or absolute_url")

        location = payload.get("location")
        location_text = location.get("name") if isinstance(location, dict) else None
        departments = payload.get("departments", [])
        tags = [
            str(department["name"])
            for department in departments
            if isinstance(department, dict) and department.get("name")
        ] if isinstance(departments, list) else []

        return NormalizedJob(
            source=self.ats_type,
            external_id=str(job_id),
            url=url,
            title=title,
            description=payload.get("content"),
            location_text=location_text,
            remote_scope=infer_remote_scope(location_text, title, payload.get("content")),
            employment_type=None,
            seniority=None,
            salary_text=None,
            tags=tags,
            posted_at=parse_datetime(payload.get("updated_at")),
            raw_payload=payload,
        )
