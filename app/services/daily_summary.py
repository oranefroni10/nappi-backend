"""Generates daily summaries of sleep data."""

import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import pytz

from .babies_data import BabyDataManager
from ..core.settings import settings
from ..core.constants import (
    DAILY_SUMMARY_MORNING_START, DAILY_SUMMARY_MORNING_END,
    DAILY_SUMMARY_NOON_START, DAILY_SUMMARY_NOON_END,
)
from ..utils.sleep_blocks import group_into_sleep_blocks

logger = logging.getLogger(__name__)

ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")

# Time period boundaries (in local time) — from centralized constants
MORNING_START = DAILY_SUMMARY_MORNING_START
MORNING_END = DAILY_SUMMARY_MORNING_END
NOON_START = DAILY_SUMMARY_NOON_START
NOON_END = DAILY_SUMMARY_NOON_END
# Night is 6 PM to 6 AM (spans two calendar days)


@dataclass
class AwakeningCount:
    morning: int = 0
    noon: int = 0
    night: int = 0


@dataclass
class SensorAverages:
    avg_temp: Optional[float] = None
    avg_humidity: Optional[float] = None
    avg_noise: Optional[float] = None


@dataclass
class DailySummaryResult:
    baby_id: int
    summary_id: Optional[int]
    sensor_averages: SensorAverages
    awakening_counts: AwakeningCount
    data_points_processed: int
    data_points_deleted: int
    success: bool
    error: Optional[str] = None


# Used by: count_awakenings_from_sleep_blocks() (classifies block end time into morning/noon/night)
def get_time_period(dt: datetime) -> str:
    """Classify datetime into morning, noon, or night."""
    hour = dt.hour

    if MORNING_START <= hour < MORNING_END:
        return "morning"
    elif NOON_START <= hour < NOON_END:
        return "noon"
    else:
        return "night"


# Used by: generate_daily_summary() (averages temp/humidity/noise for the day)
def calculate_sensor_averages(sensor_data: List[Dict[str, Any]]) -> SensorAverages:
    """Compute mean temp, humidity, noise from sensor data points."""
    if not sensor_data:
        return SensorAverages()

    temps = [d["temp_celcius"] for d in sensor_data if d.get("temp_celcius") is not None]
    humidities = [d["humidity"] for d in sensor_data if d.get("humidity") is not None]
    noises = [d["noise_decibel"] for d in sensor_data if d.get("noise_decibel") is not None]

    return SensorAverages(
        avg_temp=round(sum(temps) / len(temps), 2) if temps else None,
        avg_humidity=round(sum(humidities) / len(humidities), 2) if humidities else None,
        avg_noise=round(sum(noises) / len(noises), 2) if noises else None
    )


# Used by: generate_daily_summary() (counts awakenings per time period using sleep blocks)
def count_awakenings_from_sleep_blocks(
    events: List[Dict[str, Any]],
    timezone: pytz.timezone = ISRAEL_TZ
) -> AwakeningCount:
    """Groups events into sleep blocks, classifies each block end by period."""
    counts = AwakeningCount()

    if not events:
        return counts

    blocks = group_into_sleep_blocks(events, source="events_for_period")

    for block in blocks:
        block_end = block.block_end
        # Convert to Israel time for period classification
        if block_end.tzinfo is None:
            block_end = pytz.utc.localize(block_end)
        local_time = block_end.astimezone(timezone)

        period = get_time_period(local_time)
        if period == "morning":
            counts.morning += 1
        elif period == "noon":
            counts.noon += 1
        else:
            counts.night += 1

    return counts


# Used by: run_daily_summary_job() (generates summary for a single baby)
async def generate_daily_summary(
    baby_id: int,
    summary_date: date,
    start_time: datetime,
    end_time: datetime,
) -> DailySummaryResult:
    """Generate daily summary for one baby over the given time range."""
    logger.info(f"Generating daily summary for baby {baby_id} on {summary_date}")

    baby_manager = BabyDataManager()

    try:
        sensor_data = await baby_manager.get_sensor_data_range(
            baby_id=baby_id,
            start_time=start_time,
            end_time=end_time
        )

        data_points = len(sensor_data)
        logger.info(f"Found {data_points} sensor data points for baby {baby_id}")

        averages = calculate_sensor_averages(sensor_data)

        events = await baby_manager.get_awakening_events_for_period(
            baby_id=baby_id,
            start_time=start_time,
            end_time=end_time
        )

        logger.info(f"Found {len(events)} awakening events for baby {baby_id}")

        total_counts = count_awakenings_from_sleep_blocks(events)

        logger.info(
            f"Awakening counts for baby {baby_id}: "
            f"morning={total_counts.morning}, noon={total_counts.noon}, night={total_counts.night}"
        )

        summary_id = await baby_manager.insert_daily_summary(
            baby_id=baby_id,
            summary_date=summary_date,
            avg_humidity=averages.avg_humidity,
            avg_temp=averages.avg_temp,
            avg_noise=averages.avg_noise,
            morning_awakes_sum=total_counts.morning,
            noon_awakes_sum=total_counts.noon,
            night_awakes_sum=total_counts.night
        )

        if summary_id is None:
            return DailySummaryResult(
                baby_id=baby_id,
                summary_id=None,
                sensor_averages=averages,
                awakening_counts=total_counts,
                data_points_processed=data_points,
                data_points_deleted=0,
                success=False,
                error="Failed to insert daily summary"
            )

        deleted_count = await baby_manager.delete_sleep_data_for_period(
            baby_id=baby_id,
            start_time=start_time,
            end_time=end_time
        )

        logger.info(
            f"Daily summary {summary_id} created for baby {baby_id}, "
            f"deleted {deleted_count} sensor data rows"
        )

        return DailySummaryResult(
            baby_id=baby_id,
            summary_id=summary_id,
            sensor_averages=averages,
            awakening_counts=total_counts,
            data_points_processed=data_points,
            data_points_deleted=deleted_count,
            success=True
        )

    except Exception as e:
        logger.error(f"Error generating daily summary for baby {baby_id}: {e}", exc_info=True)
        return DailySummaryResult(
            baby_id=baby_id,
            summary_id=None,
            sensor_averages=SensorAverages(),
            awakening_counts=AwakeningCount(),
            data_points_processed=0,
            data_points_deleted=0,
            success=False,
            error=str(e)
        )


# Used by: scheduler.py (CronTrigger at 10:00 AM Israel time)
async def run_daily_summary_job() -> Dict[str, Any]:
    """Generate daily summaries for all babies (previous 24h, scheduled 10 AM Israel)."""
    logger.info("=" * 60)
    logger.info("Starting daily summary job")
    logger.info("=" * 60)

    now_israel = datetime.now(ISRAEL_TZ)
    summary_date = (now_israel - timedelta(days=1)).date()
    end_time = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(days=1)

    start_time_utc = start_time.astimezone(pytz.utc).replace(tzinfo=None)
    end_time_utc = end_time.astimezone(pytz.utc).replace(tzinfo=None)

    logger.info(f"Processing period: {start_time} to {end_time} (Israel time)")
    logger.info(f"Summary date: {summary_date}")

    baby_manager = BabyDataManager()

    try:
        babies = await baby_manager.get_babies_list()

        if not babies:
            logger.warning("No babies found in database")
            return {
                "success": True,
                "summary_date": str(summary_date),
                "babies_processed": 0,
                "results": []
            }

        logger.info(f"Processing {len(babies)} babies")

        results = []
        success_count = 0

        for baby in babies:
            result = await generate_daily_summary(
                baby_id=baby.id,
                summary_date=summary_date,
                start_time=start_time_utc,
                end_time=end_time_utc,
            )

            results.append({
                "baby_id": baby.id,
                "baby_name": baby.first_name,
                "success": result.success,
                "summary_id": result.summary_id,
                "data_points_processed": result.data_points_processed,
                "data_points_deleted": result.data_points_deleted,
                "avg_temp": result.sensor_averages.avg_temp,
                "avg_humidity": result.sensor_averages.avg_humidity,
                "avg_noise": result.sensor_averages.avg_noise,
                "morning_awakes": result.awakening_counts.morning,
                "noon_awakes": result.awakening_counts.noon,
                "night_awakes": result.awakening_counts.night,
                "error": result.error
            })

            if result.success:
                success_count += 1

        logger.info("=" * 60)
        logger.info(
            f"Daily summary job complete: {success_count}/{len(babies)} babies processed successfully"
        )
        logger.info("=" * 60)

        return {
            "success": True,
            "summary_date": str(summary_date),
            "babies_processed": len(babies),
            "babies_succeeded": success_count,
            "results": results
        }

    except Exception as e:
        logger.error(f"Fatal error in daily summary job: {e}", exc_info=True)
        return {
            "success": False,
            "summary_date": str(summary_date),
            "error": str(e),
            "results": []
        }
