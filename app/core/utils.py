import os
from typing import Dict

SENSOR_TO_ENDPOINT_MAP: Dict[str, str] = {
    "temperature": "/temperature",
    "humidity": "/humidity",
    "pressure": "/pressure",
    "camera": "/camera"
}


class Config:
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/nappi")

    SENSOR_API_BASE_URL: str = os.getenv("SENSOR_API_BASE_URL", "http://localhost:8000")

    SENSOR_POLL_INTERVAL_SECONDS: int = int(os.getenv("SENSOR_POLL_INTERVAL_SECONDS", "5"))

    CORS_ORIGINS: list = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


config = Config()