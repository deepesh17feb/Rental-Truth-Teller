"""
scripts/scheduler.py
─────────────────────
APScheduler-based cron runner for the Tier-0 crawlers.
Runs all spiders on a configurable schedule.

Usage:
    python scripts/scheduler.py               # Uses cron from .env
    python scripts/scheduler.py --now         # Run once immediately, then schedule
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("scheduler")

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SPIDERS = ["magicbricks", "99acres"]

# Default: run at 06:00 daily
DEFAULT_CRON = "0 6 * * *"


def run_all_crawlers() -> None:
    """Invoke the shell orchestrator script."""
    log.info("Scheduled crawl triggered → running all spiders…")
    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "run_crawlers.sh")],
        cwd=str(PROJECT_ROOT),
        capture_output=False,
    )
    if result.returncode != 0:
        log.error("Crawl run finished with errors (exit code %d)", result.returncode)
    else:
        log.info("Crawl run completed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="RentalTruth crawler scheduler")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Execute one crawl immediately before starting the schedule",
    )
    parser.add_argument(
        "--cron",
        default=DEFAULT_CRON,
        help=f"Cron expression for schedule (default: '{DEFAULT_CRON}')",
    )
    args = parser.parse_args()

    cron_expr = args.cron
    log.info("Scheduler starting. Cron = '%s'", cron_expr)

    if args.now:
        log.info("--now flag set: running crawl immediately…")
        run_all_crawlers()

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    # Parse cron parts: minute hour day month day_of_week
    cron_parts = cron_expr.split()
    if len(cron_parts) != 5:
        log.error("Invalid cron expression: '%s'. Must have 5 parts.", cron_expr)
        sys.exit(1)

    scheduler.add_job(
        run_all_crawlers,
        trigger=CronTrigger(
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
            timezone="Asia/Kolkata",
        ),
        id="bangalore_property_crawl",
        name="Bangalore Property Crawl",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    log.info("Scheduler started. Next runs:")
    for job in scheduler.get_jobs():
        log.info("  %s → %s", job.name, job.next_run_time)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
