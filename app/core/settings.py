"""App settings — loaded from environment variables with defaults."""

import os
from typing import List
from dotenv import load_dotenv
from app.core.constants import (
    CORRELATION_CHANGE_THRESHOLDS as _DEFAULT_CORRELATION_THRESHOLDS,
    CORRELATION_TIME_WINDOW_MINUTES as _DEFAULT_CORRELATION_WINDOW,
)

load_dotenv()


class Settings:
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    DATABASE_URL: str = os.getenv("DB_CONNECTION_STRING")
    
    SENSOR_API_BASE_URL: str = os.getenv("SENSOR_API_BASE_URL", "http://192.168.117.254:8001")
    SENSOR_POLL_INTERVAL_SECONDS: int = int(os.getenv("SENSOR_POLL_INTERVAL_SECONDS", "5"))
    
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]
    CORS_EXTRA_ORIGINS: str = os.getenv("CORS_EXTRA_ORIGINS", "")
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL_CHAT: str = os.getenv("GEMINI_MODEL_CHAT", "models/gemini-2.5-flash")
    GEMINI_MODEL_INSIGHTS: str = os.getenv("GEMINI_MODEL_INSIGHTS", "models/gemini-2.5-flash")
    
    # Defaults from constants.py; CORRELATION_TIME_WINDOW_MINUTES overridable via env
    CORRELATION_CHANGE_THRESHOLDS: dict = _DEFAULT_CORRELATION_THRESHOLDS
    CORRELATION_TIME_WINDOW_MINUTES: int = int(
        os.getenv("CORRELATION_TIME_WINDOW_MINUTES", str(_DEFAULT_CORRELATION_WINDOW))
    )
    
    DAILY_SUMMARY_HOUR: int = int(os.getenv("DAILY_SUMMARY_HOUR", "10"))
    DAILY_SUMMARY_TIMEZONE: str = os.getenv("DAILY_SUMMARY_TIMEZONE", "Asia/Jerusalem")
    
    # Generate keys with: npx web-push generate-vapid-keys
    VAPID_PUBLIC_KEY: str = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "")
    VAPID_EMAIL: str = os.getenv("VAPID_EMAIL", "admin@nappi.app")


settings = Settings()
