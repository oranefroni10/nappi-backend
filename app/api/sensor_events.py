"""
Sensor Event Endpoints - Handles sleep start/end events from M5 sensors.

These endpoints allow the M5 sensors to notify the backend when a baby
falls asleep or wakes up, enabling targeted sensor data collection.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

from .models import (
    SleepEventRequest,
    SleepStartResponse,
    AwakeningEventResponse,
    LastSensorReadings,
)
from ..services.sleep_state import get_sleep_state_manager
from ..services.babies_data import BabyDataManager
from ..services.correlation_analyzer import generate_quick_insight

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensor", tags=["sensor-events"])


@router.post("/sleep-start", response_model=SleepStartResponse)
async def sleep_start(request: SleepEventRequest):
    """
    Called by M5 sensor when it detects that a baby has fallen asleep.
    
    This starts sensor data collection for the specified baby.
    """
    baby_id = request.baby_id
    logger.info(f"Received sleep-start event for baby {baby_id}")
    
    # Validate baby exists
    baby_manager = BabyDataManager()
    babies = await baby_manager.get_babies_list()
    baby_exists = any(b.id == baby_id for b in babies)
    
    if not baby_exists:
        logger.warning(f"Sleep-start event for unknown baby {baby_id}")
        raise HTTPException(status_code=404, detail=f"Baby with id {baby_id} not found")
    
    # Register baby as sleeping
    sleep_state = get_sleep_state_manager()
    session = await sleep_state.start_sleep(baby_id)
    
    return SleepStartResponse(
        baby_id=baby_id,
        sleep_started_at=session.start_time,
        message=f"Sleep tracking started for baby {baby_id}"
    )


@router.post("/sleep-end", response_model=AwakeningEventResponse)
async def sleep_end(request: SleepEventRequest):
    """
    Called by M5 sensor when it detects that a baby has woken up.
    
    This stops sensor data collection for the specified baby and
    records an awakening event with full metadata.
    """
    baby_id = request.baby_id
    awakened_at = datetime.utcnow()
    logger.info(f"Received sleep-end event for baby {baby_id}")
    
    # End the sleep session
    sleep_state = get_sleep_state_manager()
    session = await sleep_state.end_sleep(baby_id)
    
    if session is None:
        logger.warning(f"Sleep-end event for baby {baby_id} who wasn't marked as sleeping")
        raise HTTPException(
            status_code=400, 
            detail=f"Baby {baby_id} was not marked as sleeping"
        )
    
    # Calculate sleep duration
    sleep_duration = (awakened_at - session.start_time).total_seconds() / 60.0
    
    # Get last sensor readings before wake
    baby_manager = BabyDataManager()
    last_readings = await baby_manager.get_last_sensor_readings(baby_id)
    
    last_sensor_readings = None
    if last_readings:
        last_sensor_readings = LastSensorReadings(
            temp_celcius=last_readings.get("temp_celcius"),
            humidity=last_readings.get("humidity"),
            noise_decibel=last_readings.get("noise_decibel"),
            heart_rate=last_readings.get("heart_rate"),
            recorded_at=last_readings.get("datetime"),
        )
    
    # Record awakening event in database
    event_metadata = {
        "sleep_started_at": session.start_time.isoformat(),
        "awakened_at": awakened_at.isoformat(),
        "sleep_duration_minutes": sleep_duration,
        "last_sensor_readings": {
            "temp_celcius": last_readings.get("temp_celcius") if last_readings else None,
            "humidity": last_readings.get("humidity") if last_readings else None,
            "noise_decibel": last_readings.get("noise_decibel") if last_readings else None,
            "heart_rate": last_readings.get("heart_rate") if last_readings else None,
        } if last_readings else None
    }
    
    event_id = await baby_manager.set_baby_awaking_event(baby_id, event_metadata)
    
    if event_id is None:
        logger.error(f"Failed to record awakening event for baby {baby_id}")
        raise HTTPException(
            status_code=500,
            detail="Failed to record awakening event"
        )
    
    logger.info(
        f"Recorded awakening event {event_id} for baby {baby_id}: "
        f"slept for {sleep_duration:.1f} minutes"
    )
    
    # Generate quick AI insight and update the event (non-blocking)
    try:
        quick_insight = await generate_quick_insight(
            baby_id=baby_id,
            awakened_at=awakened_at,
            sleep_duration_minutes=sleep_duration,
            last_sensor_readings=last_readings
        )
        
        if quick_insight:
            await baby_manager.update_awakening_event_insight(event_id, quick_insight)
            logger.info(f"Added AI insight to awakening event {event_id}")
    except Exception as e:
        # Don't fail the endpoint if insight generation fails
        logger.warning(f"Failed to generate quick insight for baby {baby_id}: {e}")
    
    return AwakeningEventResponse(
        baby_id=baby_id,
        event_id=event_id,
        sleep_started_at=session.start_time,
        awakened_at=awakened_at,
        sleep_duration_minutes=round(sleep_duration, 2),
        last_sensor_readings=last_sensor_readings,
        message=f"Awakening recorded: baby {baby_id} slept for {sleep_duration:.1f} minutes"
    )


@router.get("/sleep-status/{baby_id}")
async def get_sleep_status(baby_id: int):
    """
    Check if a specific baby is currently sleeping.
    """
    sleep_state = get_sleep_state_manager()
    session = await sleep_state.get_sleep_session(baby_id)
    
    if session:
        duration = (datetime.utcnow() - session.start_time).total_seconds() / 60.0
        return {
            "baby_id": baby_id,
            "is_sleeping": True,
            "sleep_started_at": session.start_time.isoformat(),
            "sleep_duration_minutes": round(duration, 2)
        }
    
    return {
        "baby_id": baby_id,
        "is_sleeping": False
    }


@router.get("/sleeping-babies")
async def get_sleeping_babies():
    """
    Get list of all babies currently sleeping.
    """
    sleep_state = get_sleep_state_manager()
    sleeping_ids = await sleep_state.get_sleeping_babies()
    
    return {
        "count": len(sleeping_ids),
        "sleeping_baby_ids": sleeping_ids
    }


@router.post("/baby-away")
async def baby_away(request: SleepEventRequest):
    """
    Called by M5 sensor when it detects that the baby is no longer in range.
    
    This stops sleep tracking WITHOUT creating an awakening event.
    Use this when the baby is moved away from the sensor (e.g., taken out of crib)
    rather than when the baby wakes up naturally.
    """
    baby_id = request.baby_id
    logger.info(f"Received baby-away event for baby {baby_id}")
    
    # End the sleep session without creating awakening event
    sleep_state = get_sleep_state_manager()
    session = await sleep_state.end_sleep(baby_id)
    
    if session is None:
        logger.info(f"Baby-away event for baby {baby_id} who wasn't marked as sleeping")
        return {
            "baby_id": baby_id,
            "was_sleeping": False,
            "message": f"Baby {baby_id} was not marked as sleeping"
        }
    
    # Calculate how long they were tracked
    away_at = datetime.utcnow()
    tracking_duration = (away_at - session.start_time).total_seconds() / 60.0
    
    logger.info(
        f"Baby {baby_id} left sensor area after {tracking_duration:.1f} minutes of tracking"
    )
    
    return {
        "baby_id": baby_id,
        "was_sleeping": True,
        "tracking_started_at": session.start_time.isoformat(),
        "away_at": away_at.isoformat(),
        "tracking_duration_minutes": round(tracking_duration, 2),
        "message": f"Sleep tracking stopped for baby {baby_id} (baby away from sensor)"
    }

