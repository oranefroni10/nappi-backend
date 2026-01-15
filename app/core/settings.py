import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DB_CONNECTION_STRING")
    
    # Sensor API Configuration
    SENSOR_API_BASE_URL: str = os.getenv("SENSOR_API_BASE_URL", "http://localhost:8001")
    SENSOR_POLL_INTERVAL_SECONDS: int = int(os.getenv("SENSOR_POLL_INTERVAL_SECONDS", "5"))
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Gemini AI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    # Model options: gemini-2.5-pro-preview-05-06 (best), gemini-2.5-flash (fast & reliable)
    GEMINI_MODEL_CHAT: str = os.getenv("GEMINI_MODEL_CHAT", "models/gemini-2.5-flash")
    GEMINI_MODEL_INSIGHTS: str = os.getenv("GEMINI_MODEL_INSIGHTS", "models/gemini-2.5-flash")
    
    # Correlation Analysis Configuration
    CORRELATION_CHANGE_THRESHOLD_PERCENT: float = float(
        os.getenv("CORRELATION_CHANGE_THRESHOLD_PERCENT", "10.0")
    )
    CORRELATION_TIME_WINDOW_MINUTES: int = int(
        os.getenv("CORRELATION_TIME_WINDOW_MINUTES", "60")
    )
    
    # Daily Summary Configuration
    DAILY_SUMMARY_HOUR: int = int(os.getenv("DAILY_SUMMARY_HOUR", "10"))
    DAILY_SUMMARY_TIMEZONE: str = os.getenv("DAILY_SUMMARY_TIMEZONE", "Asia/Jerusalem")
    
    # Web Push (VAPID) Configuration
    # Generate keys with: npx web-push generate-vapid-keys
    VAPID_PUBLIC_KEY: str = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "")
    VAPID_EMAIL: str = os.getenv("VAPID_EMAIL", "admin@nappi.app")


# Create a single instance to be imported throughout the app
settings = Settings()

