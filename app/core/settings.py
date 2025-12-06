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


# Create a single instance to be imported throughout the app
settings = Settings()

