"""Run the collectors once and exit.

This is the free-hosting friendly alternative to the always-on APScheduler worker
in ``worker/main.py``: a scheduler such as GitHub Actions starts it every hour,
it does one full pass, and it exits.

Usage (from the repository root, with PYTHONPATH pointing at ``api``):

    python -m worker.run_once              # discovery, ATS companies, public boards
    python -m worker.run_once discovery    # only find new company boards
    python -m worker.run_once companies    # only the configured ATS company boards
    python -m worker.run_once boards       # only Remotiko / TrulyRemoteWork / Dynamite
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.discovery.service import run_discovery
from app.models.event import Event
from worker.main import BOARD_COLLECTORS, collect_board_source, collect_configured_companies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openhunt.run_once")

STEPS = ("discovery", "companies", "boards")


def run_discovery_once() -> None:
    with SessionLocal() as db:
        try:
            run_discovery(db)
        except Exception as error:  # one failing step must not stop the others
            db.rollback()
            logger.exception("Company discovery failed")
            try:
                db.add(
                    Event(
                        entity_type="discovery",
                        entity_id=None,
                        action="run_failed",
                        details={"error_type": type(error).__name__, "error": str(error)[:1000]},
                    )
                )
                db.commit()
            except SQLAlchemyError:
                db.rollback()
                logger.exception("Could not persist the discovery failure event")


def run_steps(steps: list[str]) -> None:
    # Discovery runs first so boards it adds are collected in the same pass.
    if "discovery" in steps:
        run_discovery_once()
    if "companies" in steps:
        collect_configured_companies()
    if "boards" in steps:
        for source in BOARD_COLLECTORS:
            collect_board_source(source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run openHunt collectors once.")
    parser.add_argument(
        "steps",
        nargs="*",
        choices=[*STEPS, "all"],
        default=["all"],
        help="which steps to run (default: all)",
    )
    arguments = parser.parse_args(argv)
    selected = list(STEPS) if "all" in arguments.steps else arguments.steps
    run_steps(selected)
    logger.info("Finished steps: %s", ", ".join(selected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
