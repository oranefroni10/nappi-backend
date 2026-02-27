"""Pydantic models mirroring the Nappi database schema."""

# Generated from database schema — regenerate with 'python generate_models.py'
# WARNING: regeneration overwrites this file — re-add manual additions from the bottom section

from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
from decimal import Decimal


# Not currently imported — alert_service.py uses its own Alert dataclass
class Alerts(BaseModel):
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


# Used by: babies_data.py (awakening data)
class AwakeningEvents(BaseModel):
    id: int
    baby_id: Optional[int] = None
    event_metadata: Optional[dict] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies_data.py, tasks.py, auth_manager.py
class Babies(BaseModel):
    id: int
    first_name: str
    last_name: str
    birthdate: date
    gender: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies_data.py
class Correlations(BaseModel):
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


# Used by: babies_data.py
class DailySummary(BaseModel):
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


# Used by: babies_data.py (optimal environment stats)
class OptimalStats(BaseModel):
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


# Not currently imported — push_service.py uses raw SQL
class PushSubscriptions(BaseModel):
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


# Used by: babies_data.py
class SleepRealtimeData(BaseModel):
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


# Used by: auth_manager.py (aliased as User)
class Users(BaseModel):
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


# MANUAL ADDITIONS - Keep these after regenerating models
# Used by: auth_manager.py
User = Users


# Used by: auth.py (login/signup response)
class BabyResponse(BaseModel):
    """Baby info returned in API responses."""
    id: int
    first_name: str
    last_name: str
    birthdate: date

    class Config:
        from_attributes = True
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
        }


# Used by: babies.py, babies_data.py
class BabyNote(BaseModel):
    """Notes: allergies, health, preferences."""
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
