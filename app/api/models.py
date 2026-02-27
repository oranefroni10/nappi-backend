"""Pydantic request/response models for all API endpoints."""

from pydantic import BaseModel, field_validator
from datetime import datetime, date
from typing import List, Optional, Literal


class LastSleepSummary(BaseModel):
    baby_name: str
    started_at: datetime
    ended_at: datetime
    total_sleep_minutes: int
    awakenings_count: int
    avg_temperature: Optional[float] = None
    avg_humidity: Optional[float] = None
    max_noise: Optional[float] = None


class RoomMetrics(BaseModel):
    temperature_c: Optional[float] = None
    humidity_percent: Optional[float] = None
    noise_db: Optional[float] = None
    measured_at: Optional[datetime] = None
    notes: Optional[str] = None


# Sensor event models (M5 sleep detection)

class SleepEventRequest(BaseModel):
    baby_id: int


class SleepStartResponse(BaseModel):
    baby_id: int
    sleep_started_at: datetime
    message: str


class LastSensorReadings(BaseModel):
    temp_celcius: Optional[float] = None
    humidity: Optional[float] = None
    noise_decibel: Optional[float] = None
    recorded_at: Optional[datetime] = None


class AwakeningEventResponse(BaseModel):
    baby_id: int
    event_id: int
    sleep_started_at: datetime
    awakened_at: datetime
    sleep_duration_minutes: float
    last_sensor_readings: Optional[LastSensorReadings] = None
    message: str


# Statistics models

class SensorDataPoint(BaseModel):
    date: date
    value: float


class SensorStatsResponse(BaseModel):
    baby_id: int
    sensor: Literal["temperature", "humidity", "noise"]
    start_date: date
    end_date: date
    data: List[SensorDataPoint]


class SleepPattern(BaseModel):
    cluster_id: int
    label: str  # "Morning nap", "Afternoon nap", "Night sleep"
    avg_start: str  # "08:45"
    avg_end: str  # "10:50"
    avg_duration_hours: float
    session_count: int
    earliest_start: str
    latest_end: str


class SleepPatternsResponse(BaseModel):
    baby_id: int
    month: int
    year: int
    total_sessions: int
    patterns: List[SleepPattern]


class DailySleepPoint(BaseModel):
    date: date
    total_hours: float
    sessions_count: int
    awakenings_count: int


class DailySleepResponse(BaseModel):
    baby_id: int
    start_date: date
    end_date: date
    data: List[DailySleepPoint]


class OptimalStatsResponse(BaseModel):
    baby_id: int
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    noise: Optional[float] = None
    has_data: bool  # False if not enough data yet


# AI-powered insights models

class StructuredInsightResponse(BaseModel):
    likely_cause: str
    actionable_tips: List[str]
    environment_assessment: str
    age_context: str
    sleep_quality_note: str


class EnhancedInsightsResponse(BaseModel):
    baby_id: int
    event_id: Optional[int] = None
    awakened_at: Optional[datetime] = None
    sleep_duration_minutes: Optional[float] = None
    environmental_changes: dict
    insights: Optional[StructuredInsightResponse] = None
    simple_insight: Optional[str] = None
    correlation_id: Optional[int] = None


# Trend analysis models

class AgeRecommendation(BaseModel):
    min_hours: int
    max_hours: int
    typical_naps: str
    night_hours: str


class WeeklyTrend(BaseModel):
    avg_sleep_hours: float
    trend: str  # "improving", "declining", "stable"
    trend_percentage: float
    consistency_score: float
    total_sessions: int
    avg_sessions_per_day: float
    best_day: Optional[str] = None
    worst_day: Optional[str] = None


class MonthlyTrend(BaseModel):
    avg_sleep_hours: float
    trend: str
    trend_percentage: float
    consistency_score: float
    total_sessions: int


class AITrendInsights(BaseModel):
    summary: str
    highlights: List[str]
    concerns: List[str]
    recommendations: List[str]
    age_comparison: str


class TrendsResponse(BaseModel):
    baby_id: int
    baby_name: str
    age_months: int
    age_recommendation: AgeRecommendation
    weekly: Optional[WeeklyTrend] = None
    monthly: Optional[MonthlyTrend] = None
    ai_insights: Optional[AITrendInsights] = None


# Schedule prediction models

class WakeWindowRange(BaseModel):
    min: float
    max: float


class NextSleepPrediction(BaseModel):
    predicted_time: datetime
    predicted_time_formatted: str
    confidence: str  # "high", "medium", "low"
    type: str  # "nap" or "bedtime"
    based_on: str
    minutes_until: int
    wake_window_status: str


class SchedulePredictionResponse(BaseModel):
    baby_id: int
    generated_at: datetime
    wake_window_range_hours: WakeWindowRange
    optimal_bedtime: str  # "HH:MM"
    current_wake_duration_minutes: Optional[int] = None
    next_sleep: Optional[NextSleepPrediction] = None
    suggestions: List[str]


# AI summary models (combined for home dashboard)

class EnvironmentStatus(BaseModel):
    status: str  # "optimal", "needs_attention", "unknown"
    temperature_status: Optional[str] = None
    humidity_status: Optional[str] = None
    noise_status: Optional[str] = None
    message: str


class SleepQualitySummary(BaseModel):
    last_sleep_hours: Optional[float] = None
    trend_direction: Optional[str] = None  # "improving", "stable", "declining"
    message: str


class AISummaryResponse(BaseModel):
    baby_id: int
    baby_name: str
    generated_at: datetime
    
    sleep_summary: SleepQualitySummary
    environment: EnvironmentStatus
    
    next_sleep_prediction: Optional[str] = None
    next_sleep_time: Optional[str] = None
    
    todays_tip: str
    
    weekly_trend: Optional[str] = None
    trend_message: Optional[str] = None
    
    quick_insights: List[str]
