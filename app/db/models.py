# Generated from database schema - DO NOT EDIT MANUALLY
# Run 'python generate_models.py' to regenerate

from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
from decimal import Decimal


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


class Babies(BaseModel):
    """
    Represents the Nappi.babies table
    """
    id: int
    first_name: str
    last_name: str
    birthdate: date
    gender: Optional[str] = None
    notes: Optional[str] = None  # Parent notes: allergies, conditions, health info
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


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


class DailySummary(BaseModel):
    """
    Represents the Nappi.daily_summary table
    """
    id: int
    baby_id: int
    avg_humidity: Optional[float] = None
    avg_temp: Optional[float] = None
    avg_noise: Optional[float] = None
    anomalies: Optional[dict] = None
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


class OptimalStats(BaseModel):
    """
    Represents the Nappi.optimal_stats table
    """
    id: int
    baby_id: Optional[int] = None
    temperature: Optional[float] = None
    humidity : Optional[float] = None
    noise: Optional[float] = None
    heart_rate: Optional[float] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


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
    heart_rate: Optional[float] = None
    sleep_quality_score: Optional[int] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


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

# Alias for backward compatibility (auth_manager.py uses singular name)
User = Users


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
