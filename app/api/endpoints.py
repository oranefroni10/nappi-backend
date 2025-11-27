from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from .models import LastSleepSummary, SleepStageMetric, RoomMetrics

router = APIRouter()


@router.get("/sleep/latest", response_model=LastSleepSummary)
async def get_last_sleep_summary():
    end = datetime.utcnow()
    start = end - timedelta(hours=8)

    stages = [
        SleepStageMetric(
            stage="light",
            start_time=start,
            end_time=start + timedelta(hours=1.5),
        ),
        SleepStageMetric(
            stage="deep",
            start_time=start + timedelta(hours=1.5),
            end_time=start + timedelta(hours=5),
        ),
        SleepStageMetric(
            stage="rem",
            start_time=start + timedelta(hours=5),
            end_time=end,
        ),
    ]

    return LastSleepSummary(
        baby_name="Noa",
        started_at=start,
        ended_at=end,
        total_sleep_minutes=8 * 60,
        awakenings_count=2,
        sleep_quality_score=87,
        stages=stages,
    )


@router.get("/room/current", response_model=RoomMetrics)
async def get_current_room_metrics():
    return RoomMetrics(
        temperature_c=22.7,
        humidity_percent=47.0,
        noise_db=32.5,
        light_lux=15.0,
        measured_at=datetime.utcnow(),
        notes="Room is quiet and slightly dark.",
    )

