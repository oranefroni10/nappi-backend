"""
Statistics API Endpoints - Provides data for the Statistics page graphs.

Endpoints:
- GET /stats/sensors - Sensor averages over time (from daily_summary)
- GET /stats/sleep-patterns - Sleep time patterns with clustering (from awakening_events)
- GET /stats/daily-sleep - Daily sleep totals (from awakening_events)
"""

import logging
from datetime import date, datetime, timedelta
from typing import Literal
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from .models import (
    SensorDataPoint,
    SensorStatsResponse,
    SleepPattern,
    SleepPatternsResponse,
    DailySleepPoint,
    DailySleepResponse,
)
from ..services.babies_data import BabyDataManager
from ..services.sleep_patterns import analyze_sleep_patterns

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["statistics"])

# Validation constants
MIN_DAYS = 7
MAX_DAYS = 90  # 3 months


def validate_date_range(start_date: date, end_date: date) -> None:
    """Validate date range is within allowed bounds."""
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date must be after start_date"
        )
    
    days_diff = (end_date - start_date).days
    
    if days_diff < MIN_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range must be at least {MIN_DAYS} days"
        )
    
    if days_diff > MAX_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range cannot exceed {MAX_DAYS} days (3 months)"
        )


async def validate_baby_exists(baby_id: int) -> None:
    """Validate that the baby exists in the database."""
    baby_manager = BabyDataManager()
    exists = await baby_manager.baby_exists(baby_id)
    
    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Baby with id {baby_id} not found"
        )


@router.get("/sensors", response_model=SensorStatsResponse)
async def get_sensor_stats(
    baby_id: int = Query(..., description="Baby ID"),
    sensor: Literal["temperature", "humidity", "noise"] = Query(..., description="Sensor type"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)")
):
    """
    Get sensor averages over a time range for graphing.
    
    Data comes from daily_summary table (one point per day).
    Minimum 7 days, maximum 90 days (3 months).
    """
    # Validate inputs
    validate_date_range(start_date, end_date)
    await validate_baby_exists(baby_id)
    
    # Map sensor name to database column
    sensor_column_map = {
        "temperature": "avg_temp",
        "humidity": "avg_humidity",
        "noise": "avg_noise"
    }
    db_column = sensor_column_map[sensor]
    
    # Fetch data
    baby_manager = BabyDataManager()
    summaries = await baby_manager.get_daily_summaries_range(
        baby_id=baby_id,
        start_date=start_date,
        end_date=end_date
    )
    
    # Build response data points
    data_points = []
    for summary in summaries:
        value = summary.get(db_column)
        if value is not None:
            data_points.append(SensorDataPoint(
                date=summary["summary_date"],
                value=round(value, 2)
            ))
    
    logger.info(
        f"Retrieved {len(data_points)} sensor data points for baby {baby_id} "
        f"({sensor}, {start_date} to {end_date})"
    )
    
    return SensorStatsResponse(
        baby_id=baby_id,
        sensor=sensor,
        start_date=start_date,
        end_date=end_date,
        data=data_points
    )


@router.get("/sleep-patterns", response_model=SleepPatternsResponse)
async def get_sleep_patterns(
    baby_id: int = Query(..., description="Baby ID"),
    month: int = Query(None, ge=1, le=12, description="Month (1-12), defaults to current"),
    year: int = Query(None, description="Year, defaults to current")
):
    """
    Get sleep time patterns for a specific month.
    
    Returns clustered sleep time windows with averaged start/end times.
    Useful for parents to understand when the baby typically sleeps.
    """
    # Default to current month/year
    now = datetime.now()
    if month is None:
        month = now.month
    if year is None:
        year = now.year
    
    await validate_baby_exists(baby_id)
    
    # Fetch sleep sessions for the month
    baby_manager = BabyDataManager()
    raw_sessions = await baby_manager.get_sleep_sessions_for_month(
        baby_id=baby_id,
        year=year,
        month=month
    )
    
    # Analyze patterns using clustering
    patterns_data = analyze_sleep_patterns(raw_sessions)
    
    # Convert to Pydantic models
    patterns = [
        SleepPattern(
            cluster_id=p["cluster_id"],
            label=p["label"],
            avg_start=p["avg_start"],
            avg_end=p["avg_end"],
            avg_duration_hours=p["avg_duration_hours"],
            session_count=p["session_count"],
            earliest_start=p["earliest_start"],
            latest_end=p["latest_end"]
        )
        for p in patterns_data
    ]
    
    total_sessions = sum(p.session_count for p in patterns)
    
    logger.info(
        f"Analyzed {total_sessions} sleep sessions for baby {baby_id} "
        f"({year}-{month:02d}), found {len(patterns)} patterns"
    )
    
    return SleepPatternsResponse(
        baby_id=baby_id,
        month=month,
        year=year,
        total_sessions=total_sessions,
        patterns=patterns
    )


@router.get("/daily-sleep", response_model=DailySleepResponse)
async def get_daily_sleep(
    baby_id: int = Query(..., description="Baby ID"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)")
):
    """
    Get total sleep hours per day over a time range.
    
    Returns daily sleep totals and session counts for graphing.
    Minimum 7 days, maximum 90 days (3 months).
    """
    # Validate inputs
    validate_date_range(start_date, end_date)
    await validate_baby_exists(baby_id)
    
    # Fetch sleep sessions
    baby_manager = BabyDataManager()
    sessions = await baby_manager.get_sleep_sessions_for_range(
        baby_id=baby_id,
        start_date=start_date,
        end_date=end_date
    )
    
    # Aggregate by date
    daily_data = defaultdict(lambda: {"total_minutes": 0.0, "sessions": 0})
    
    for session in sessions:
        session_date = session.get("session_date")
        duration = session.get("duration_minutes") or 0.0
        
        if session_date:
            daily_data[session_date]["total_minutes"] += duration
            daily_data[session_date]["sessions"] += 1
    
    # Build response data points
    data_points = []
    for day_date, stats in sorted(daily_data.items()):
        data_points.append(DailySleepPoint(
            date=day_date,
            total_hours=round(stats["total_minutes"] / 60.0, 2),
            sessions_count=stats["sessions"]
        ))
    
    logger.info(
        f"Retrieved daily sleep data for baby {baby_id}: "
        f"{len(data_points)} days with data ({start_date} to {end_date})"
    )
    
    return DailySleepResponse(
        baby_id=baby_id,
        start_date=start_date,
        end_date=end_date,
        data=data_points
    )

