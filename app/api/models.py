from pydantic import BaseModel, field_validator
from datetime import datetime, date
from typing import List, Optional, Literal


class LastSleepSummary(BaseModel):
    baby_name: str
    started_at: datetime
    ended_at: datetime
    total_sleep_minutes: int
    awakenings_count: int
    sleep_quality_score: int
    avg_temperature: Optional[float] = None
    avg_humidity: Optional[float] = None
    max_noise: Optional[float] = None


class RoomMetrics(BaseModel):
    temperature_c: Optional[float] = None
    humidity_percent: Optional[float] = None
    noise_db: Optional[float] = None
    measured_at: Optional[datetime] = None
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


# ============================================
# AI-Powered Insights Models
# ============================================

# --- Structured Insights ---

class StructuredInsightResponse(BaseModel):
    """Structured multi-section AI insight."""
    likely_cause: str
    actionable_tips: List[str]
    environment_assessment: str
    age_context: str
    sleep_quality_note: str


class EnhancedInsightsResponse(BaseModel):
    """Enhanced insights response with structured and simple versions."""
    baby_id: int
    event_id: Optional[int] = None
    awakened_at: Optional[datetime] = None
    sleep_duration_minutes: Optional[float] = None
    environmental_changes: dict
    insights: Optional[StructuredInsightResponse] = None
    simple_insight: Optional[str] = None
    correlation_id: Optional[int] = None


# --- Trend Analysis ---

class AgeRecommendation(BaseModel):
    """Sleep recommendations based on baby's age."""
    min_hours: int
    max_hours: int
    typical_naps: str
    night_hours: str


class WeeklyTrend(BaseModel):
    """7-day trend analysis."""
    avg_sleep_hours: float
    trend: str  # "improving", "declining", "stable"
    trend_percentage: float
    consistency_score: float
    total_sessions: int
    avg_sessions_per_day: float
    best_day: Optional[str] = None
    worst_day: Optional[str] = None


class MonthlyTrend(BaseModel):
    """30-day trend analysis."""
    avg_sleep_hours: float
    trend: str
    trend_percentage: float
    consistency_score: float
    total_sessions: int


class AITrendInsights(BaseModel):
    """AI-generated insights about trends."""
    summary: str
    highlights: List[str]
    concerns: List[str]
    recommendations: List[str]
    age_comparison: str


class TrendsResponse(BaseModel):
    """Complete trend analysis response."""
    baby_id: int
    baby_name: str
    age_months: int
    age_recommendation: AgeRecommendation
    weekly: Optional[WeeklyTrend] = None
    monthly: Optional[MonthlyTrend] = None
    ai_insights: Optional[AITrendInsights] = None


# --- Schedule Prediction ---

class WakeWindowRange(BaseModel):
    """Wake window range in hours."""
    min: float
    max: float


class NextSleepPrediction(BaseModel):
    """Prediction for next sleep window."""
    predicted_time: datetime
    predicted_time_formatted: str
    confidence: str  # "high", "medium", "low"
    type: str  # "nap" or "bedtime"
    based_on: str
    minutes_until: int
    wake_window_status: str


class SchedulePredictionResponse(BaseModel):
    """Response for schedule prediction."""
    baby_id: int
    generated_at: datetime
    wake_window_range_hours: WakeWindowRange
    optimal_bedtime: str  # "HH:MM" format
    current_wake_duration_minutes: Optional[int] = None
    next_sleep: Optional[NextSleepPrediction] = None
    suggestions: List[str]


# --- AI Summary (Combined for Home Dashboard) ---

class EnvironmentStatus(BaseModel):
    """Current environment status assessment."""
    status: str  # "optimal", "needs_attention", "unknown"
    temperature_status: Optional[str] = None
    humidity_status: Optional[str] = None
    noise_status: Optional[str] = None
    message: str


class SleepQualitySummary(BaseModel):
    """Summary of recent sleep quality."""
    last_sleep_hours: Optional[float] = None
    last_sleep_quality: Optional[str] = None  # "good", "fair", "poor"
    trend_direction: Optional[str] = None  # "improving", "stable", "declining"
    message: str


class AISummaryResponse(BaseModel):
    """Comprehensive AI summary for home dashboard."""
    baby_id: int
    baby_name: str
    generated_at: datetime
    
    # Sleep quality summary
    sleep_summary: SleepQualitySummary
    
    # Environment check
    environment: EnvironmentStatus
    
    # Next sleep prediction
    next_sleep_prediction: Optional[str] = None
    next_sleep_time: Optional[str] = None
    
    # Today's tip
    todays_tip: str
    
    # Trend indicator
    weekly_trend: Optional[str] = None
    trend_message: Optional[str] = None
    
    # Quick insights list
    quick_insights: List[str]
