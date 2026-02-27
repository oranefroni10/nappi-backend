"""
Sensor event endpoints — sleep lifecycle from M5 hardware + parent manual override.

Routes (/sensor):
  POST /sleep-start          - M5 reports baby fell asleep (ignored during cooldown)
  POST /sleep-end            - M5 reports baby woke up; creates awakening event + alert
  POST /baby-away            - M5 reports baby removed from crib; stops tracking silently
  POST /intervention         - Parent manual override (mark asleep/awake); starts 20min cooldown
  GET  /sleep-status/{baby_id}    - Current sleep state for a baby
  GET  /sleeping-babies          - List all currently sleeping babies (debug)
  GET  /cooldown-status/{baby_id} - Check if intervention cooldown is active
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
)
from ..services.sleep_state import get_sleep_state_manager, INTERVENTION_COOLDOWN_MINUTES
from ..services.babies_data import BabyDataManager
from ..services.correlation_analyzer import generate_quick_insight
from ..services.alert_service import get_alert_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensor", tags=["sensor-events"])


class InterventionRequest(BaseModel):
    baby_id: int
    action: str  # "mark_asleep" | "mark_awake"


class InterventionResponse(BaseModel):
    baby_id: int
    status: str  # "sleeping" | "awake"
    cooldown_minutes: int
    cooldown_until: str
    message: str


class CooldownIgnoredResponse(BaseModel):
    ignored: bool
    reason: str
    cooldown_remaining_minutes: Optional[int]


# Used by: M5 sensor — baby fell asleep, starts sensor data collection
@router.post("/sleep-start", response_model=SleepStartResponse)
async def sleep_start(request: SleepEventRequest):
    """Ignored if parent intervention cooldown is active."""
    baby_id = request.baby_id
    logger.info(f"Received sleep-start event for baby {baby_id}")
    
    sleep_state = get_sleep_state_manager()
    if await sleep_state.is_in_cooldown(baby_id):
        remaining = await sleep_state.get_cooldown_remaining(baby_id)
        logger.info(f"Ignoring sensor sleep-start for baby {baby_id} - in cooldown ({remaining} min remaining)")
        raise HTTPException(
            status_code=200,  # not an error, just ignored
            detail={
                "ignored": True,
                "reason": "intervention_cooldown",
                "cooldown_remaining_minutes": remaining
            }
        )
    
    baby_manager = BabyDataManager()
    babies = await baby_manager.get_babies_list()
    baby_exists = any(b.id == baby_id for b in babies)
    
    if not baby_exists:
        logger.warning(f"Sleep-start event for unknown baby {baby_id}")
        raise HTTPException(status_code=404, detail=f"Baby with id {baby_id} not found")
    
    session = await sleep_state.start_sleep(baby_id)
    
    return SleepStartResponse(
        baby_id=baby_id,
        sleep_started_at=session.start_time,
        message=f"Sleep tracking started for baby {baby_id}"
    )


# Used by: M5 sensor — baby woke up; creates awakening event + alert
@router.post("/sleep-end", response_model=AwakeningEventResponse)
async def sleep_end(request: SleepEventRequest):
    """Ignored if parent intervention cooldown is active."""
    baby_id = request.baby_id
    awakened_at = datetime.utcnow()
    logger.info(f"Received sleep-end event for baby {baby_id}")
    
    sleep_state = get_sleep_state_manager()
    if await sleep_state.is_in_cooldown(baby_id):
        remaining = await sleep_state.get_cooldown_remaining(baby_id)
        logger.info(f"Ignoring sensor sleep-end for baby {baby_id} - in cooldown ({remaining} min remaining)")
        raise HTTPException(
            status_code=200,
            detail={
                "ignored": True,
                "reason": "intervention_cooldown",
                "cooldown_remaining_minutes": remaining
            }
        )
    
    session = await sleep_state.end_sleep(baby_id)
    
    if session is None:
        logger.warning(f"Sleep-end event for baby {baby_id} who wasn't marked as sleeping")
        raise HTTPException(
            status_code=400, 
            detail=f"Baby {baby_id} was not marked as sleeping"
        )
    
    sleep_duration = (awakened_at - session.start_time).total_seconds() / 60.0
    
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
        raise HTTPException(status_code=500, detail="Failed to record awakening event")
    
    logger.info(
        f"Recorded awakening event {event_id} for baby {baby_id}: "
        f"slept for {sleep_duration:.1f} minutes"
    )
    
    # optional AI insight — failure won't block the response
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
        logger.warning(f"Failed to generate quick insight for baby {baby_id}: {e}")
    
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


# Used by: Home Dashboard — sleep status indicator; Notifications page — polling
@router.get("/sleep-status/{baby_id}")
async def get_sleep_status(baby_id: int):
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


# Used by: Internal/debug — lists all currently sleeping babies
@router.get("/sleeping-babies")
async def get_sleeping_babies():
    sleep_state = get_sleep_state_manager()
    sleeping_ids = await sleep_state.get_sleeping_babies()
    
    return {
        "count": len(sleeping_ids),
        "sleeping_baby_ids": sleeping_ids
    }


# Used by: M5 sensor — baby removed from crib; stops tracking without awakening event
@router.post("/baby-away")
async def baby_away(request: SleepEventRequest):
    baby_id = request.baby_id
    logger.info(f"Received baby-away event for baby {baby_id}")
    
    sleep_state = get_sleep_state_manager()
    session = await sleep_state.end_sleep(baby_id)
    
    if session is None:
        logger.info(f"Baby-away event for baby {baby_id} who wasn't marked as sleeping")
        return {
            "baby_id": baby_id,
            "was_sleeping": False,
            "message": f"Baby {baby_id} was not marked as sleeping"
        }
    
    away_at = datetime.utcnow()
    tracking_duration = (away_at - session.start_time).total_seconds() / 60.0
    
    logger.info(f"Baby {baby_id} left sensor area after {tracking_duration:.1f} minutes of tracking")
    
    return {
        "baby_id": baby_id,
        "was_sleeping": True,
        "tracking_started_at": session.start_time.isoformat(),
        "away_at": away_at.isoformat(),
        "tracking_duration_minutes": round(tracking_duration, 2),
        "message": f"Sleep tracking stopped for baby {baby_id} (baby away from sensor)"
    }


# Used by: Home Dashboard — parent manual sleep override with 20min cooldown
@router.post("/intervention", response_model=InterventionResponse)
async def parent_intervention(request: InterventionRequest):
    """
    Parent manually sets sleep state. Does NOT create an alert.
    Starts a 20-minute cooldown to ignore sensor events.
    """
    baby_id = request.baby_id
    action = request.action.lower()
    
    if action not in ("mark_asleep", "mark_awake"):
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'mark_asleep' or 'mark_awake'")
    
    logger.info(f"Parent intervention for baby {baby_id}: {action}")
    
    baby_manager = BabyDataManager()
    babies = await baby_manager.get_babies_list()
    baby_exists = any(b.id == baby_id for b in babies)
    
    if not baby_exists:
        raise HTTPException(status_code=404, detail=f"Baby with id {baby_id} not found")
    
    sleep_state = get_sleep_state_manager()
    cooldown_until = await sleep_state.start_intervention_cooldown(baby_id)
    
    if action == "mark_asleep":
        session = await sleep_state.start_sleep(baby_id)
        return InterventionResponse(
            baby_id=baby_id,
            status="sleeping",
            cooldown_minutes=INTERVENTION_COOLDOWN_MINUTES,
            cooldown_until=cooldown_until.isoformat(),
            message=f"Baby {baby_id} marked as sleeping. Sensor events ignored for {INTERVENTION_COOLDOWN_MINUTES} minutes."
        )
    else:
        # end sleep without recording awakening event (parent already knows)
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


# Used by: Home Dashboard — checks if intervention cooldown is active
@router.get("/cooldown-status/{baby_id}")
async def get_cooldown_status(baby_id: int):
    sleep_state = get_sleep_state_manager()
    in_cooldown = await sleep_state.is_in_cooldown(baby_id)
    remaining = await sleep_state.get_cooldown_remaining(baby_id) if in_cooldown else None
    
    return {
        "baby_id": baby_id,
        "in_cooldown": in_cooldown,
        "cooldown_remaining_minutes": remaining,
        "message": f"Sensor events will be ignored for {remaining} more minutes" if in_cooldown else "No active cooldown"
    }
