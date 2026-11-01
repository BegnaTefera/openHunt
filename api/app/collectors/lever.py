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


class LeverCollector(PublicCollector):
    ats_type = "lever"
    endpoint = "https://api.lever.co/v0/postings/{slug}?mode=json&skip={skip}&limit={limit}"
    page_size = 100

    def fetch(self, company: Company) -> list[dict[str, Any]]:
        all_jobs: list[dict[str, Any]] = []
        skip = 0
        while True:
            url = self.endpoint.format(
                slug=quote(company.ats_slug, safe=""),
                skip=skip,
                limit=self.page_size,
            )
            payload = fetch_json(url)
            if not isinstance(payload, list):
                raise CollectorError("Lever response must be a JSON array")
            if not all(isinstance(job, dict) for job in payload):
                raise CollectorError("Lever response array contains a malformed item")
            all_jobs.extend(payload)
            if len(payload) < self.page_size:
                return all_jobs
            skip += len(payload)

    def normalize(self, company: Company, payload: dict[str, Any]) -> NormalizedJob:
        job_id = payload.get("id")
        title = payload.get("text")
        url = payload.get("hostedUrl") or payload.get("applyUrl")
        if not job_id or not isinstance(title, str) or not isinstance(url, str):
            raise CollectorError("Lever posting is missing id, text, or hostedUrl/applyUrl")

        categories = payload.get("categories")
        categories = categories if isinstance(categories, dict) else {}
        category_values = [
            str(value)
            for value in categories.values()
            if isinstance(value, str) and value.strip()
        ]
        description = payload.get("descriptionPlain") or payload.get("description")
        return NormalizedJob(
            source=self.ats_type,
            external_id=str(job_id),
            url=url,
            title=title,
            description=description if isinstance(description, str) else None,
            location_text=categories.get("location"),
            remote_scope=infer_remote_scope(
                categories.get("location"),
                title,
                description,
            ),
            employment_type=categories.get("commitment"),
            seniority=None,
            salary_text=None,
            tags=category_values,
            posted_at=parse_datetime(payload.get("createdAt")),
            raw_payload=payload,
        )
