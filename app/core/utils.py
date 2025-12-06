from typing import Dict

# Map sensor names to API endpoints (with baby_id placeholder)
SENSOR_TO_ENDPOINT_MAP: Dict[str, str] = {
    "temperature": "/temperature/{baby_id}",
    "humidity": "/humidity/{baby_id}",
    "noise_decibel": "/noise_decibel/{baby_id}",
    "heart_rate": "/heart_rate/{baby_id}"
}

# Map sensor names to database column names
SENSOR_TO_DB_COLUMN_MAP: Dict[str, str] = {
    "temperature": "temp_celcius",
    "humidity": "humidity",
    "noise_decibel": "noise_decibel",
    "heart_rate": "heart_rate",
}