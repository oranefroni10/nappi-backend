"""Shared lookup maps — sensor names to API endpoints and DB columns."""

from typing import Dict

# Used by: scheduler.py, tasks.py, endpoints.py, stats.py — sensor name → API endpoint
SENSOR_TO_ENDPOINT_MAP: Dict[str, str] = {
    "temperature": "/temperature/{baby_id}",
    "humidity": "/humidity/{baby_id}",
    "noise_decibel": "/noise_decibel/{baby_id}",
}

# Used by: tasks.py, endpoints.py, stats.py — sensor name → DB column name
SENSOR_TO_DB_COLUMN_MAP: Dict[str, str] = {
    "temperature": "temp_celcius",
    "humidity": "humidity",
    "noise_decibel": "noise_decibel",
}
