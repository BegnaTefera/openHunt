from __future__ import annotations

from app.collectors.ashby import AshbyCollector
from app.collectors.base import Collector, CollectorUnavailableError
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector

COLLECTORS: dict[str, type[Collector]] = {
    "greenhouse": GreenhouseCollector,
    "lever": LeverCollector,
    "ashby": AshbyCollector,
}


def get_collector(ats_type: str) -> Collector:
    try:
        return COLLECTORS[ats_type]()
    except KeyError as error:
        raise CollectorUnavailableError(
            f"No public collector is enabled for ATS type {ats_type!r}"
        ) from error
