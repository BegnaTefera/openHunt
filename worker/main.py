from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.collectors.base import (
    CollectorError,
    CollectorUnavailableError,
    sync_board_jobs,
    sync_company_jobs,
)
from app.collectors.board_common import BoardCollector
from app.collectors.dynamitejobs import DynamiteJobsCollector
from app.collectors.registry import get_collector
from app.collectors.remotiko import RemotikoCollector
from app.collectors.trulyremotework import TrulyRemoteWorkCollector
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.event import Event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openhunt.worker")

BOARD_COLLECTORS: dict[str, type[BoardCollector]] = {
    "remotiko": RemotikoCollector,
    "trulyremotework": TrulyRemoteWorkCollector,
    "dynamitejobs": DynamiteJobsCollector,
}


def collect_configured_companies() -> None:
    with SessionLocal() as db:
        companies = db.scalars(select(Company).order_by(Company.id)).all()
        for company in companies:
            try:
                collector = get_collector(company.ats_type)
                jobs = collector.collect(company)
                inserted = sync_company_jobs(db, company, jobs)
                db.commit()
                logger.info(
                    "Synchronized %s jobs from %s (%s)",
                    len(jobs),
                    company.name,
                    inserted,
                )
            except CollectorUnavailableError as error:
                logger.warning("Skipping %s: %s", company.name, error)
            except (CollectorError, SQLAlchemyError, ValueError):
                db.rollback()
                logger.exception("Collector failed for company %s", company.name)


def collect_board_source(source: str) -> None:
    collector_type = BOARD_COLLECTORS.get(source)
    if collector_type is None:
        raise ValueError(f"Unknown public-board source: {source}")

    with SessionLocal() as db:
        try:
            snapshot = collector_type().collect()
            inserted = sync_board_jobs(
                db,
                source=source,
                jobs=snapshot.jobs,
                complete_snapshot=snapshot.complete,
            )
            db.commit()
            logger.info(
                "Synchronized %s jobs from %s (%s inserted; complete=%s)",
                len(snapshot.jobs),
                source,
                inserted,
                snapshot.complete,
            )
        except Exception as error:
            db.rollback()
            logger.exception("Public-board collector failed for %s", source)
            try:
                db.add(
                    Event(
                        entity_type="job_source",
                        entity_id=None,
                        action="collector_failed",
                        details={
                            "source": source,
                            "error_type": type(error).__name__,
                            "error": str(error)[:1000],
                        },
                    )
                )
                db.commit()
            except SQLAlchemyError:
                db.rollback()
                logger.exception("Could not persist collector failure event for %s", source)


def main() -> None:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        collect_configured_companies,
        "interval",
        minutes=settings.job_fetch_interval_minutes,
        id="collect-public-job-boards",
        max_instances=1,
        coalesce=True,
    )
    logger.info("Worker is running scheduled public job-board collectors.")
    scheduler.add_job(collect_configured_companies, "date", id="initial-collector-run")
    for source in BOARD_COLLECTORS:
        scheduler.add_job(
            collect_board_source,
            "interval",
            minutes=settings.job_fetch_interval_minutes,
            args=[source],
            id=f"collect-{source}",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            collect_board_source,
            "date",
            args=[source],
            id=f"initial-{source}-collector-run",
        )
    scheduler.start()


if __name__ == "__main__":
    main()
