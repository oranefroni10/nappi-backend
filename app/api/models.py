from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


class SleepStageMetric(BaseModel):
    stage: str
    start_time: datetime
    end_time: datetime


class LastSleepSummary(BaseModel):
    baby_name: str
    started_at: datetime
    ended_at: datetime
    total_sleep_minutes: int
    awakenings_count: int
    sleep_quality_score: int
    stages: List[SleepStageMetric]


class RoomMetrics(BaseModel):
    temperature_c: float
    humidity_percent: float
    noise_db: float
    light_lux: float
    measured_at: datetime
    notes: Optional[str] = None
