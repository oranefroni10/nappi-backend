# Generated from database schema - DO NOT EDIT MANUALLY
# Run 'python generate_models.py' to regenerate

from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
from decimal import Decimal


# Used by: alert_service.py (raw SQL mirrors this schema), alerts.py endpoints
class Alerts(BaseModel):
    """
    Represents the Nappi.alerts table
    """
    id: Optional[int] = None
    baby_id: int
    user_id: int
    type: str
    title: str
    message: str
    severity: Optional[str] = None
    metadata: Optional[dict] = None
    read: Optional[bool] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies_data.py (DB queries for awakening data)
class AwakeningEvents(BaseModel):
    """
    Represents the Nappi.awakening_events table
    """
    id: int
    baby_id: Optional[int] = None
    event_metadata: Optional[dict] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies_data.py, tasks.py (sensor polling), auth_manager.py (signup/login)
class Babies(BaseModel):
    """
    Represents the Nappi.babies table
    """
    id: int
    first_name: str
    last_name: str
    birthdate: date
    gender: Optional[str] = None
    notes: Optional[str] = None  # Legacy single-field notes on the baby record (brief health info). Detailed notes use the baby_notes table.
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies_data.py (DB queries), correlation_analyzer.py, chat_service.py
class Correlations(BaseModel):
    """
    Represents the Nappi.correlations table
    """
    id: int
    time: date
    parameters: dict
    baby_id: int
    extra_data: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies_data.py (DB queries), daily_summary.py (generation), trend_analyzer.py
class DailySummary(BaseModel):
    """
    Represents the Nappi.daily_summary table
    """
    id: int
    baby_id: int
    avg_humidity: Optional[float] = None
    avg_temp: Optional[float] = None
    avg_noise: Optional[float] = None
    morning_awakes_sum: Optional[int] = None
    noon_awakes_sum: Optional[int] = None
    night_awakes_sum: Optional[int] = None
    summary_date: Optional[date] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies_data.py (DB queries for optimal environment stats)
class OptimalStats(BaseModel):
    """
    Represents the Nappi.optimal_stats table
    """
    id: int
    baby_id: Optional[int] = None
    temperature: Optional[float] = None
    humidity : Optional[float] = None
    noise: Optional[float] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: push_service.py (Web Push subscription management, raw SQL)
class PushSubscriptions(BaseModel):
    """
    Represents the Nappi.push_subscriptions table
    """
    id: Optional[int] = None
    user_id: int
    endpoint: str
    p256dh_key: str
    auth_key: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies_data.py (sensor data queries), daily_summary.py (daily averages)
class SleepRealtimeData(BaseModel):
    """
    Represents the Nappi.sleep_realtime_data table
    """
    id: int
    baby_id: int
    datetime: datetime
    humidity: Optional[float] = None
    temp_celcius: Optional[float] = None
    noise_decibel: Optional[float] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: auth_manager.py (login/signup, aliased as User)
class Users(BaseModel):
    """
    Represents the Nappi.users table
    """
    id: int
    username: str
    password: str
    baby_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# =============================================================================
# MANUAL ADDITIONS - Keep these after regenerating models
# =============================================================================

# Used by: auth_manager.py (backward-compatible alias for Users)
User = Users


# Used by: auth.py (POST /auth/login, POST /auth/signup response)
class BabyResponse(BaseModel):
    """
    Baby info returned in API responses.
    Includes notes field for parent-provided health information.
    """
    id: int
    first_name: str
    last_name: str
    birthdate: date
    notes: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies.py (GET/POST/DELETE /babies/notes), babies_data.py (note queries)
class BabyNote(BaseModel):
    """
    Represents an individual note about a baby.
    Used for allergies, health conditions, preferences, etc.
    """
    id: int
    baby_id: int
    title: str
    content: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }
