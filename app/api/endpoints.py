"""
Dashboard endpoints - Last sleep summary and current room metrics.

These endpoints provide personalized data for the user's baby.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from .models import LastSleepSummary, SleepStageMetric, RoomMetrics
from ..core.database import get_database
from ..services.babies_data import BabyDataManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sleep/latest", response_model=LastSleepSummary)
async def get_last_sleep_summary(
    baby_id: int = Query(..., description="Baby ID to get sleep summary for")
):
    """
    Get the most recent sleep session summary for a baby.
    
    Returns data from the latest awakening event including:
    - Sleep start/end times
    - Duration
    - Quality score (if available)
    - Sleep stages (simplified)
    """
    database = get_database()
    baby_manager = BabyDataManager()
    
    # Validate baby exists
    babies = await baby_manager.get_babies_list()
    baby = next((b for b in babies if b.id == baby_id), None)
    
    if not baby:
        raise HTTPException(status_code=404, detail=f"Baby with id {baby_id} not found")
    
    try:
        # Get the most recent awakening event
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
                # No sleep data - return placeholder with baby name
                now = datetime.utcnow()
                return LastSleepSummary(
                    baby_name=baby.first_name,
                    started_at=now - timedelta(hours=2),
                    ended_at=now,
                    total_sleep_minutes=0,
                    awakenings_count=0,
                    sleep_quality_score=0,
                    stages=[]
                )
            
            metadata = row["event_metadata"] or {}
            
            # Parse timestamps from metadata
            sleep_started_str = metadata.get("sleep_started_at")
            awakened_str = metadata.get("awakened_at")
            duration_minutes = metadata.get("sleep_duration_minutes", 0)
            
            # Default timestamps if missing
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
            
            # Calculate duration if not in metadata
            if duration_minutes == 0:
                duration_minutes = (ended_at - started_at).total_seconds() / 60
            
            # Get awakening count for today
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
            
            # Generate simplified sleep stages
            total_duration = (ended_at - started_at).total_seconds()
            stages = []
            
            if total_duration > 0:
                # Simplified stage breakdown: 20% light, 50% deep, 30% REM
                light_end = started_at + timedelta(seconds=total_duration * 0.2)
                deep_end = started_at + timedelta(seconds=total_duration * 0.7)
                
                stages = [
                    SleepStageMetric(
                        stage="light",
                        start_time=started_at,
                        end_time=light_end
                    ),
                    SleepStageMetric(
                        stage="deep",
                        start_time=light_end,
                        end_time=deep_end
                    ),
                    SleepStageMetric(
                        stage="rem",
                        start_time=deep_end,
                        end_time=ended_at
                    )
                ]
            
            # Get sleep quality score from sensor data average (simplified)
            quality_result = await session.execute(
                text('''
                    SELECT AVG(sleep_quality_score) as avg_score
                    FROM "Nappi"."sleep_realtime_data"
                    WHERE baby_id = :baby_id
                      AND datetime >= :started_at
                      AND datetime <= :ended_at
                      AND sleep_quality_score IS NOT NULL
                '''),
                {"baby_id": baby_id, "started_at": started_at, "ended_at": ended_at}
            )
            avg_quality = quality_result.scalar()
            sleep_quality_score = int(avg_quality) if avg_quality else 75  # Default score
            
            return LastSleepSummary(
                baby_name=baby.first_name,
                started_at=started_at,
                ended_at=ended_at,
                total_sleep_minutes=int(duration_minutes),
                awakenings_count=awakenings_count,
                sleep_quality_score=sleep_quality_score,
                stages=stages
            )
            
    except Exception as e:
        logger.error(f"Failed to get last sleep summary for baby {baby_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve sleep data")


@router.get("/room/current", response_model=RoomMetrics)
async def get_current_room_metrics(
    baby_id: int = Query(..., description="Baby ID to get room metrics for")
):
    """
    Get the current room conditions from the latest sensor readings.
    
    Returns temperature, humidity, noise levels from the most recent sensor data.
    """
    baby_manager = BabyDataManager()
    
    # Validate baby exists
    babies = await baby_manager.get_babies_list()
    baby = next((b for b in babies if b.id == baby_id), None)
    
    if not baby:
        raise HTTPException(status_code=404, detail=f"Baby with id {baby_id} not found")
    
    try:
        # Get the most recent sensor readings
        last_readings = await baby_manager.get_last_sensor_readings(baby_id)
        
        if not last_readings:
            # No sensor data - return default values
            return RoomMetrics(
                temperature_c=22.0,
                humidity_percent=50.0,
                noise_db=30.0,
                light_lux=0.0,
                measured_at=datetime.utcnow(),
                notes="No sensor data available yet"
            )
        
        return RoomMetrics(
            temperature_c=last_readings.get("temp_celcius") or 22.0,
            humidity_percent=last_readings.get("humidity") or 50.0,
            noise_db=last_readings.get("noise_decibel") or 30.0,
            light_lux=0.0,  # Light sensor not implemented
            measured_at=last_readings.get("datetime") or datetime.utcnow(),
            notes=None
        )
        
    except Exception as e:
        logger.error(f"Failed to get room metrics for baby {baby_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve room data")
