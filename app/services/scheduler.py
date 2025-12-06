import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from .tasks import collect_and_store_baby_sensor_data_task
from .data_miner import HttpSensorSource
from ..core.settings import settings
from ..core.utils import SENSOR_TO_ENDPOINT_MAP

logger = logging.getLogger(__name__)

scheduler: Optional[AsyncIOScheduler] = None

# Initialize HTTP sensor source with reduced timeout for faster failure
_data_source = HttpSensorSource(
    base_url=settings.SENSOR_API_BASE_URL,
    endpoint_map=SENSOR_TO_ENDPOINT_MAP,
    timeout_seconds=5  # Fail fast if sensor doesn't respond
)


async def _run_baby_sensor_collection():
    """
    Wrapper function for the scheduled task.
    Collects sensor data for all babies and stores in database.
    """
    await collect_and_store_baby_sensor_data_task(_data_source)


async def start_scheduler():
    """
    Initialize and start the APScheduler.
    Schedules periodic sensor data collection for all babies.
    """
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already running")
        return

    logger.info("Initializing scheduler...")

    scheduler = AsyncIOScheduler()

    # Schedule baby sensor data collection task
    scheduler.add_job(
        _run_baby_sensor_collection,
        trigger=IntervalTrigger(seconds=settings.SENSOR_POLL_INTERVAL_SECONDS),
        id="baby_sensor_collection",
        name="Collect sensor data for all babies and store in DB",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info(
        f"Scheduler started successfully - collecting data every "
        f"{settings.SENSOR_POLL_INTERVAL_SECONDS} seconds"
    )


async def stop_scheduler():
    global scheduler

    if scheduler is None:
        logger.warning("Scheduler is not running")
        return

    logger.info("Shutting down scheduler...")
    scheduler.shutdown(wait=True)
    scheduler = None
    logger.info("Scheduler stopped")


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
