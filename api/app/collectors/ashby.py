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


class AshbyCollector(PublicCollector):
    ats_type = "ashby"
    endpoint = (
        "https://api.ashbyhq.com/posting-api/job-board/"
        "{slug}?includeCompensation=true"
    )

    def fetch(self, company: Company) -> list[dict[str, Any]]:
        payload = fetch_json(self.endpoint.format(slug=quote(company.ats_slug, safe="")))
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise CollectorError("Ashby response must contain a jobs array")
        if not all(isinstance(job, dict) for job in payload["jobs"]):
            raise CollectorError("Ashby jobs array contains a malformed item")
        return payload["jobs"]

    def normalize(self, company: Company, payload: dict[str, Any]) -> NormalizedJob:
        job_id = payload.get("id")
        title = payload.get("title")
        url = payload.get("jobUrl") or payload.get("applyUrl")
        if not job_id or not isinstance(title, str) or not isinstance(url, str):
            raise CollectorError("Ashby job is missing id, title, or jobUrl/applyUrl")

        locations: list[str] = []
        primary_location = payload.get("location")
        if isinstance(primary_location, str) and primary_location:
            locations.append(primary_location)
        secondary = payload.get("secondaryLocations", [])
        if isinstance(secondary, list):
            locations.extend(
                item["location"]
                for item in secondary
                if isinstance(item, dict) and isinstance(item.get("location"), str)
            )

        department = payload.get("department")
        team = payload.get("team")
        tags = [value for value in (department, team) if isinstance(value, str) and value]
        compensation = payload.get("compensation")
        salary = (
            compensation.get("compensationTierSummary")
            if isinstance(compensation, dict)
            else None
        )
        is_remote = payload.get("isRemote") is True
        return NormalizedJob(
            source=self.ats_type,
            external_id=str(job_id),
            url=url,
            title=title,
            description=payload.get("descriptionPlain") or payload.get("descriptionHtml"),
            location_text=", ".join(locations) or None,
            remote_scope="remote" if is_remote else infer_remote_scope(*locations, title),
            employment_type=payload.get("employmentType"),
            seniority=None,
            salary_text=salary if isinstance(salary, str) else None,
            tags=tags,
            posted_at=parse_datetime(payload.get("publishedAt")),
            raw_payload=payload,
        )
