from typing import Dict

# Used by: scheduler.py (sensor polling), tasks.py (poll_and_store_sensors), endpoints.py (GET /sleep/room-metrics)
# Map sensor names to API endpoints (with baby_id placeholder)
SENSOR_TO_ENDPOINT_MAP: Dict[str, str] = {
    "temperature": "/temperature/{baby_id}",
    "humidity": "/humidity/{baby_id}",
    "noise_decibel": "/noise_decibel/{baby_id}",
}

# Used by: tasks.py (poll_and_store_sensors), endpoints.py (GET /sleep/room-metrics)
# Map sensor names to database column names
SENSOR_TO_DB_COLUMN_MAP: Dict[str, str] = {
    "temperature": "temp_celcius",
    "humidity": "humidity",
    "noise_decibel": "noise_decibel",
}