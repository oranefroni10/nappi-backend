from pydantic import BaseModel, field_validator
from datetime import datetime, date
from typing import List, Optional, Literal


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


# ============================================
# Sensor Event Models (M5 Sleep Detection)
# ============================================

class SleepEventRequest(BaseModel):
    """Request body for sleep start/end events from M5 sensor."""
    baby_id: int


class SleepStartResponse(BaseModel):
    """Response for successful sleep start event."""
    baby_id: int
    sleep_started_at: datetime
    message: str


class LastSensorReadings(BaseModel):
    """Last sensor readings before awakening."""
    temp_celcius: Optional[float] = None
    humidity: Optional[float] = None
    noise_decibel: Optional[float] = None
    heart_rate: Optional[float] = None
    recorded_at: Optional[datetime] = None


class AwakeningEventResponse(BaseModel):
    """Response for successful awakening event with full metadata."""
    baby_id: int
    event_id: int
    sleep_started_at: datetime
    awakened_at: datetime
    sleep_duration_minutes: float
    last_sensor_readings: Optional[LastSensorReadings] = None
    message: str


# ============================================
# Statistics Models
# ============================================

# --- Sensor Stats ---

class SensorDataPoint(BaseModel):
    """Single data point for sensor graph."""
    date: date
    value: float


class SensorStatsResponse(BaseModel):
    """Response for sensor statistics over time."""
    baby_id: int
    sensor: Literal["temperature", "humidity", "noise"]
    start_date: date
    end_date: date
    data: List[SensorDataPoint]


# --- Sleep Patterns ---

class SleepPattern(BaseModel):
    """A clustered sleep pattern with averaged times."""
    cluster_id: int
    label: str  # "Morning nap", "Afternoon nap", "Night sleep"
    avg_start: str  # "08:45" format
    avg_end: str  # "10:50" format
    avg_duration_hours: float
    session_count: int
    earliest_start: str  # "07:30" - range info
    latest_end: str  # "12:00" - range info


class SleepPatternsResponse(BaseModel):
    """Response for sleep patterns analysis."""
    baby_id: int
    month: int
    year: int
    total_sessions: int
    patterns: List[SleepPattern]


# --- Daily Sleep ---

class DailySleepPoint(BaseModel):
    """Single day's sleep data."""
    date: date
    total_hours: float
    sessions_count: int


class DailySleepResponse(BaseModel):
    """Response for daily sleep totals over time."""
    baby_id: int
    start_date: date
    end_date: date
    data: List[DailySleepPoint]


# --- Optimal Stats ---

class OptimalStatsResponse(BaseModel):
    """Response for baby's optimal sleep conditions."""
    baby_id: int
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    noise: Optional[float] = None
    has_data: bool  # False if not enough data yet
