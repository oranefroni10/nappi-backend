import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from .tasks import collect_sensor_data_task
from .data_miner import HttpSensorSource
from ..core.utils import config, SENSOR_TO_ENDPOINT_MAP

logger = logging.getLogger(__name__)

scheduler: Optional[AsyncIOScheduler] = None

_data_source = HttpSensorSource(
    base_url=config.SENSOR_API_BASE_URL,
    endpoint_map=SENSOR_TO_ENDPOINT_MAP
)
_sensor_names = list(SENSOR_TO_ENDPOINT_MAP.keys())


async def _run_sensor_collection():
    await collect_sensor_data_task(_data_source, _sensor_names)


async def start_scheduler():
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already running")
        return

    logger.info("Initializing scheduler...")

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        _run_sensor_collection,
        trigger=IntervalTrigger(seconds=config.SENSOR_POLL_INTERVAL_SECONDS),
        id="sensor_data_collection",
        name="Collect data from all sensors",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()


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
