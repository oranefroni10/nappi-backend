"""
Dashboard endpoints — last sleep summary and live room conditions.

Routes (no prefix):
  GET /sleep/latest  - Last sleep session summary (duration, awakenings, avg sensors)
  GET /room/current  - Live sensor readings; falls back to last DB reading if sensors offline
"""

import asyncio
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from .models import LastSleepSummary, RoomMetrics
from ..core.database import get_database
from ..core.settings import settings
from ..core.utils import SENSOR_TO_ENDPOINT_MAP, SENSOR_TO_DB_COLUMN_MAP
from ..core.constants import SENSOR_FETCH_TIMEOUT_SECONDS
from ..services.babies_data import BabyDataManager
from ..services.data_miner import HttpSensorSource

logger = logging.getLogger(__name__)

router = APIRouter()


# Used by: Home Dashboard — last sleep summary card
@router.get("/sleep/latest", response_model=LastSleepSummary)
async def get_last_sleep_summary(
    baby_id: int = Query(..., description="Baby ID to get sleep summary for")
):
    database = get_database()
    baby_manager = BabyDataManager()
    
    babies = await baby_manager.get_babies_list()
    baby = next((b for b in babies if b.id == baby_id), None)
    
    if not baby:
        raise HTTPException(status_code=404, detail=f"Baby with id {baby_id} not found")
    
    try:
        async with database.session() as session:
            result = await session.execute(
                text('''
                    SELECT id, baby_id, event_metadata
                    FROM "Nappi"."awakening_events"
                    WHERE baby_id = :baby_id
                    ORDER BY id DESC
                    LIMIT 1
                '''),
                {"baby_id": baby_id}
            )
            row = result.mappings().first()
            
            if not row:
                now = datetime.utcnow()
                return LastSleepSummary(
                    baby_name=baby.first_name,
                    started_at=now - timedelta(hours=2),
                    ended_at=now,
                    total_sleep_minutes=0,
                    awakenings_count=0
                )
            
            metadata = row["event_metadata"] or {}
            
            sleep_started_str = metadata.get("sleep_started_at")
            awakened_str = metadata.get("awakened_at")
            duration_minutes = metadata.get("sleep_duration_minutes", 0)
            
            ended_at = datetime.utcnow()
            started_at = ended_at - timedelta(hours=2)
            
            if awakened_str:
                try:
                    ended_at = datetime.fromisoformat(awakened_str.replace("Z", "+00:00"))
                    if ended_at.tzinfo:
                        ended_at = ended_at.replace(tzinfo=None)
                except (ValueError, AttributeError):
                    pass
            
            if sleep_started_str:
                try:
                    started_at = datetime.fromisoformat(sleep_started_str.replace("Z", "+00:00"))
                    if started_at.tzinfo:
                        started_at = started_at.replace(tzinfo=None)
                except (ValueError, AttributeError):
                    pass
            
            if duration_minutes == 0:
                duration_minutes = (ended_at - started_at).total_seconds() / 60
            
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            awakenings_result = await session.execute(
                text('''
                    SELECT COUNT(*) as count
                    FROM "Nappi"."awakening_events"
                    WHERE baby_id = :baby_id
                      AND (event_metadata->>'awakened_at')::timestamp >= :today_start
                '''),
                {"baby_id": baby_id, "today_start": today_start}
            )
            awakenings_count = awakenings_result.scalar() or 0
            
            sensor_result = await session.execute(
                text('''
                    SELECT
                        AVG(temp_celcius) as avg_temp,
                        AVG(humidity) as avg_humidity,
                        MAX(noise_decibel) as max_noise
                    FROM "Nappi"."sleep_realtime_data"
                    WHERE baby_id = :baby_id
                      AND datetime >= :started_at
                      AND datetime <= :ended_at
                '''),
                {"baby_id": baby_id, "started_at": started_at, "ended_at": ended_at}
            )
            sensor_row = sensor_result.mappings().first()

            avg_temperature = float(sensor_row["avg_temp"]) if sensor_row and sensor_row["avg_temp"] is not None else None
            avg_humidity = float(sensor_row["avg_humidity"]) if sensor_row and sensor_row["avg_humidity"] is not None else None
            max_noise = float(sensor_row["max_noise"]) if sensor_row and sensor_row["max_noise"] is not None else None

            return LastSleepSummary(
                baby_name=baby.first_name,
                started_at=started_at,
                ended_at=ended_at,
                total_sleep_minutes=int(duration_minutes),
                awakenings_count=awakenings_count,
                avg_temperature=avg_temperature,
                avg_humidity=avg_humidity,
                max_noise=max_noise
            )
            
    except Exception as e:
        logger.error(f"Failed to get last sleep summary for baby {baby_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve sleep data")


# Used by: Home Dashboard — current room conditions card
@router.get("/room/current", response_model=RoomMetrics)
async def get_current_room_metrics(
    baby_id: int = Query(..., description="Baby ID to get room metrics for")
):
    """Fetches live sensor data; falls back to last DB reading if sensors unreachable."""
    baby_manager = BabyDataManager()

    babies = await baby_manager.get_babies_list()
    baby = next((b for b in babies if b.id == baby_id), None)

    if not baby:
        raise HTTPException(status_code=404, detail=f"Baby with id {baby_id} not found")

    data_source = HttpSensorSource(
        base_url=settings.SENSOR_API_BASE_URL,
        endpoint_map=SENSOR_TO_ENDPOINT_MAP,
        timeout_seconds=SENSOR_FETCH_TIMEOUT_SECONDS,
    )

    sensor_names = list(SENSOR_TO_ENDPOINT_MAP.keys())
    results = await asyncio.gather(
        *[data_source.get_sensor_data(sensor, baby_id) for sensor in sensor_names],
        return_exceptions=True,
    )

    live_data = {}
    for sensor_name, result in zip(sensor_names, results):
        if result and not isinstance(result, Exception) and isinstance(result, dict) and "value" in result:
            db_column = SENSOR_TO_DB_COLUMN_MAP.get(sensor_name)
            if db_column:
                live_data[db_column] = result["value"]

    if live_data:
        return RoomMetrics(
            temperature_c=live_data.get("temp_celcius"),
            humidity_percent=live_data.get("humidity"),
            noise_db=live_data.get("noise_decibel"),
            measured_at=datetime.utcnow(),
        )

    logger.warning(f"Live sensors unreachable for baby {baby_id}, falling back to last DB reading")
    try:
        last_readings = await baby_manager.get_last_sensor_readings(baby_id)

        if not last_readings:
            return RoomMetrics(notes="Sensors are currently unavailable and no recent data found")

        return RoomMetrics(
            temperature_c=last_readings.get("temp_celcius"),
            humidity_percent=last_readings.get("humidity"),
            noise_db=last_readings.get("noise_decibel"),
            measured_at=last_readings.get("datetime"),
            notes="Live sensors unavailable — showing last recorded data",
        )

    except Exception as e:
        logger.error(f"Failed to get room metrics for baby {baby_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve room data")
