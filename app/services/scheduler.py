"""
APScheduler setup — three recurring jobs.

Jobs:
  - Sensor collection: every SENSOR_POLL_INTERVAL_SECONDS (sleeping babies only)
  - Daily summary:     DAILY_SUMMARY_HOUR:00 (aggregates previous 24h, deletes raw data)
  - Optimal stats:     DAILY_SUMMARY_HOUR:05 (recalculates weighted optimal conditions)
"""

import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from .tasks import collect_and_store_baby_sensor_data_task
from .daily_summary import run_daily_summary_job
from .optimal_stats import run_optimal_stats_job
from .data_miner import HttpSensorSource
from ..core.settings import settings
from ..core.utils import SENSOR_TO_ENDPOINT_MAP

logger = logging.getLogger(__name__)

scheduler: Optional[AsyncIOScheduler] = None

_data_source = HttpSensorSource(
    base_url=settings.SENSOR_API_BASE_URL,
    endpoint_map=SENSOR_TO_ENDPOINT_MAP,
    timeout_seconds=5  # Fail fast if sensor doesn't respond
)


# Used by: start_scheduler
async def _run_baby_sensor_collection():
    """Collects sensor data for sleeping babies and stores in DB."""
    await collect_and_store_baby_sensor_data_task(_data_source)


# Used by: main (lifespan startup)
async def start_scheduler():
    """Initialize and start APScheduler."""
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already running")
        return

    logger.info("Initializing scheduler...")

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        _run_baby_sensor_collection,
        trigger=IntervalTrigger(seconds=settings.SENSOR_POLL_INTERVAL_SECONDS),
        id="baby_sensor_collection",
        name="Collect sensor data for all babies and store in DB",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        run_daily_summary_job,
        trigger=CronTrigger(
            hour=settings.DAILY_SUMMARY_HOUR,
            minute=0,
            timezone=settings.DAILY_SUMMARY_TIMEZONE
        ),
        id="daily_summary_generation",
        name="Generate daily summaries for all babies",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        run_optimal_stats_job,
        trigger=CronTrigger(
            hour=settings.DAILY_SUMMARY_HOUR,
            minute=5,
            timezone=settings.DAILY_SUMMARY_TIMEZONE
        ),
        id="optimal_stats_calculation",
        name="Calculate optimal stats for all babies",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info(
        f"Scheduler started successfully:\n"
        f"  - Sensor collection: every {settings.SENSOR_POLL_INTERVAL_SECONDS} seconds\n"
        f"  - Daily summary: {settings.DAILY_SUMMARY_HOUR}:00 {settings.DAILY_SUMMARY_TIMEZONE}\n"
        f"  - Optimal stats: {settings.DAILY_SUMMARY_HOUR}:05 {settings.DAILY_SUMMARY_TIMEZONE}"
    )


# Used by: main (lifespan shutdown)
async def stop_scheduler():
    global scheduler

    if scheduler is None:
        logger.warning("Scheduler is not running")
        return

    logger.info("Shutting down scheduler...")
    scheduler.shutdown(wait=True)
    scheduler = None
    logger.info("Scheduler stopped")


# Used by: not currently called (available for health/debug endpoints)
def get_scheduler_status() -> dict:
    global scheduler

    if scheduler is None:
        return {
            "running": False,
            "jobs": []
        }

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        })

    return {
        "running": scheduler.running,
        "jobs": jobs
    }
