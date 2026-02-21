"""
Sensor Event Endpoints - Handles sleep start/end events from M5 sensors.

These endpoints allow the M5 sensors to notify the backend when a baby
falls asleep or wakes up, enabling targeted sensor data collection.

Also provides parent intervention endpoint for manual sleep state override
with 20-minute cooldown to ignore sensor events after intervention.
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .models import (
    SleepEventRequest,
    SleepStartResponse,
    AwakeningEventResponse,
    LastSensorReadings,
    BulkSensorRequest,
    BulkSensorResponse,
)
from ..services.sleep_state import get_sleep_state_manager, INTERVENTION_COOLDOWN_MINUTES
from ..services.babies_data import BabyDataManager
from ..services.correlation_analyzer import generate_quick_insight
from ..services.alert_service import get_alert_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensor", tags=["sensor-events"])


# ============================================
# Intervention Models
# ============================================

class InterventionRequest(BaseModel):
    """Request for parent intervention."""
    baby_id: int
    action: str  # "mark_asleep" | "mark_awake"


class InterventionResponse(BaseModel):
    """Response for parent intervention."""
    baby_id: int
    status: str  # "sleeping" | "awake"
    cooldown_minutes: int
    cooldown_until: str
    message: str


class CooldownIgnoredResponse(BaseModel):
    """Response when event is ignored due to cooldown."""
    ignored: bool
    reason: str
    cooldown_remaining_minutes: Optional[int]


# Used by: M5 sensor — notifies backend when baby falls asleep
@router.post("/sleep-start", response_model=SleepStartResponse)
async def sleep_start(request: SleepEventRequest):
    """
    Called by M5 sensor when it detects that a baby has fallen asleep.
    
    This starts sensor data collection for the specified baby.
    
    Note: If a parent intervention cooldown is active, this event will be ignored.
    """
    baby_id = request.baby_id
    logger.info(f"Received sleep-start event for baby {baby_id}")
    
    # Check if in intervention cooldown - ignore sensor events
    sleep_state = get_sleep_state_manager()
    if await sleep_state.is_in_cooldown(baby_id):
        remaining = await sleep_state.get_cooldown_remaining(baby_id)
        logger.info(f"Ignoring sensor sleep-start for baby {baby_id} - in cooldown ({remaining} min remaining)")
        raise HTTPException(
            status_code=200,  # Not an error, just ignored
            detail={
                "ignored": True,
                "reason": "intervention_cooldown",
                "cooldown_remaining_minutes": remaining
            }
        )
    
    # Validate baby exists
    baby_manager = BabyDataManager()
    babies = await baby_manager.get_babies_list()
    baby_exists = any(b.id == baby_id for b in babies)
    
    if not baby_exists:
        logger.warning(f"Sleep-start event for unknown baby {baby_id}")
        raise HTTPException(status_code=404, detail=f"Baby with id {baby_id} not found")
    
    # Register baby as sleeping
    session = await sleep_state.start_sleep(baby_id)
    
    return SleepStartResponse(
        baby_id=baby_id,
        sleep_started_at=session.start_time,
        message=f"Sleep tracking started for baby {baby_id}"
    )


# Used by: M5 sensor — notifies backend when baby wakes up; creates awakening event + alert
@router.post("/sleep-end", response_model=AwakeningEventResponse)
async def sleep_end(request: SleepEventRequest):
    """
    Called by M5 sensor when it detects that a baby has woken up.
    
    This stops sensor data collection for the specified baby and
    records an awakening event with full metadata.
    
    Note: If a parent intervention cooldown is active, this event will be ignored.
    """
    baby_id = request.baby_id
    awakened_at = datetime.utcnow()
    logger.info(f"Received sleep-end event for baby {baby_id}")
    
    # Check if in intervention cooldown - ignore sensor events
    sleep_state = get_sleep_state_manager()
    if await sleep_state.is_in_cooldown(baby_id):
        remaining = await sleep_state.get_cooldown_remaining(baby_id)
        logger.info(f"Ignoring sensor sleep-end for baby {baby_id} - in cooldown ({remaining} min remaining)")
        raise HTTPException(
            status_code=200,  # Not an error, just ignored
            detail={
                "ignored": True,
                "reason": "intervention_cooldown",
                "cooldown_remaining_minutes": remaining
            }
        )
    
    # End the sleep session
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
    
    # Create awakening alert (sensor detected wake - parent should be notified)
    try:
        alert_service = get_alert_service()
        await alert_service.create_awakening_alert(
            baby_id=baby_id,
            sleep_duration_minutes=sleep_duration,
            awakened_at=awakened_at,
            last_sensor_readings=last_readings
        )
        logger.info(f"Created awakening alert for baby {baby_id}")
    except Exception as e:
        # Don't fail the endpoint if alert creation fails
        logger.warning(f"Failed to create awakening alert for baby {baby_id}: {e}")
    
    return AwakeningEventResponse(
        baby_id=baby_id,
        event_id=event_id,
        sleep_started_at=session.start_time,
        awakened_at=awakened_at,
        sleep_duration_minutes=round(sleep_duration, 2),
        last_sensor_readings=last_sensor_readings,
        message=f"Awakening recorded: baby {baby_id} slept for {sleep_duration:.1f} minutes"
    )


# Used by: Home Dashboard — sleep status indicator; Notifications page — sleep state polling
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


# Used by: Internal/debug — lists all currently sleeping babies (APScheduler polling target)
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


# Used by: M5 sensor — baby removed from crib; stops tracking without creating awakening event
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


# ============================================
# Bulk Sensor Data (M5 offline buffer sync)
# ============================================

# Used by: M5 sensor — sends buffered readings after WiFi reconnect to fill data gaps
@router.post("/bulk-readings", response_model=BulkSensorResponse)
async def bulk_readings(request: BulkSensorRequest):
    """
    Accept batch of buffered sensor readings from M5 device.

    Called after WiFi reconnection to backfill data that was collected
    while the device was offline. Each reading has a device-provided
    timestamp so the data slots into the correct time position.
    """
    if not request.readings:
        return BulkSensorResponse(inserted=0, message="No readings provided")

    logger.info(f"Received {len(request.readings)} buffered readings from M5")

    baby_manager = BabyDataManager()
    inserted = await baby_manager.insert_bulk_sleep_realtime_data(request.readings)

    return BulkSensorResponse(
        inserted=inserted,
        message=f"Inserted {inserted} offline readings"
    )


# ============================================
# Parent Intervention Endpoints
# ============================================

# Used by: Home Dashboard — parent manual sleep override (mark asleep/awake) with 20min cooldown
@router.post("/intervention", response_model=InterventionResponse)
async def parent_intervention(request: InterventionRequest):
    """
    Parent manually sets sleep state, overriding sensor detection.
    
    This endpoint:
    - Does NOT create an alert (parent already knows)
    - Starts a 20-minute cooldown to ignore sensor sleep/awake events
    - Immediately changes the sleep state
    
    Use when:
    - Parent sees via camera that baby is awake/asleep but sensor got it wrong
    - Parent wants to manually start/stop sleep tracking
    
    Args:
        request.baby_id: The baby ID
        request.action: "mark_asleep" or "mark_awake"
    """
    baby_id = request.baby_id
    action = request.action.lower()
    
    if action not in ("mark_asleep", "mark_awake"):
        raise HTTPException(
            status_code=400,
            detail="Invalid action. Must be 'mark_asleep' or 'mark_awake'"
        )
    
    logger.info(f"Parent intervention for baby {baby_id}: {action}")
    
    # Validate baby exists
    baby_manager = BabyDataManager()
    babies = await baby_manager.get_babies_list()
    baby_exists = any(b.id == baby_id for b in babies)
    
    if not baby_exists:
        raise HTTPException(status_code=404, detail=f"Baby with id {baby_id} not found")
    
    sleep_state = get_sleep_state_manager()
    
    # Start cooldown - ignore sensor events for 20 minutes
    cooldown_until = await sleep_state.start_intervention_cooldown(baby_id)
    
    if action == "mark_asleep":
        # Start sleep session
        session = await sleep_state.start_sleep(baby_id)
        return InterventionResponse(
            baby_id=baby_id,
            status="sleeping",
            cooldown_minutes=INTERVENTION_COOLDOWN_MINUTES,
            cooldown_until=cooldown_until.isoformat(),
            message=f"Baby {baby_id} marked as sleeping. Sensor events ignored for {INTERVENTION_COOLDOWN_MINUTES} minutes."
        )
    else:  # mark_awake
        # End sleep session WITHOUT recording awakening event
        # (parent already knows, no alert needed)
        session = await sleep_state.end_sleep(baby_id)
        
        if session:
            duration = (datetime.utcnow() - session.start_time).total_seconds() / 60.0
            logger.info(f"Parent intervention ended sleep for baby {baby_id} after {duration:.1f} minutes")
        
        return InterventionResponse(
            baby_id=baby_id,
            status="awake",
            cooldown_minutes=INTERVENTION_COOLDOWN_MINUTES,
            cooldown_until=cooldown_until.isoformat(),
            message=f"Baby {baby_id} marked as awake. Sensor events ignored for {INTERVENTION_COOLDOWN_MINUTES} minutes."
        )


# Used by: Home Dashboard — checks if intervention cooldown is active for UI feedback
@router.get("/cooldown-status/{baby_id}")
async def get_cooldown_status(baby_id: int):
    """
    Check if a baby is in intervention cooldown.
    
    Returns the cooldown status and remaining time if applicable.
    """
    sleep_state = get_sleep_state_manager()
    in_cooldown = await sleep_state.is_in_cooldown(baby_id)
    remaining = await sleep_state.get_cooldown_remaining(baby_id) if in_cooldown else None
    
    return {
        "baby_id": baby_id,
        "in_cooldown": in_cooldown,
        "cooldown_remaining_minutes": remaining,
        "message": f"Sensor events will be ignored for {remaining} more minutes" if in_cooldown else "No active cooldown"
    }

