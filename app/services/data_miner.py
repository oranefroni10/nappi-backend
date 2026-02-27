"""HTTP client for fetching live sensor readings from the M5 hardware API."""

import aiohttp
import logging
from typing import Protocol, Optional, Dict, Any

logger = logging.getLogger(__name__)


# Used by: type hint protocol for HttpSensorSource (not instantiated directly)
class SensorDataSource(Protocol):
    # Used by: tasks.py (_process_single_baby), endpoints.py (GET /room/current)
    async def get_sensor_data(self, sensor_name: str, baby_id: int) -> Optional[Dict[str, Any]]:
        """Fetch sensor data for a specific baby"""
        ...


# Used by: scheduler.py (module-level singleton), endpoints.py (GET /room/current), tasks.py (type hint)
class HttpSensorSource:
    """HTTP-based sensor data source with baby-specific endpoints."""

    # Used by: scheduler.py (module-level instantiation), endpoints.py (GET /room/current)
    def __init__(self, base_url: str, endpoint_map: Dict[str, str], timeout_seconds: int = 5):
        self.base_url = base_url
        self.endpoint_map = endpoint_map
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    # Used by: tasks.py (_process_single_baby), endpoints.py (GET /room/current)
    async def get_sensor_data(self, sensor_name: str, baby_id: int) -> Optional[Dict[str, Any]]:

        if sensor_name not in self.endpoint_map:
            logger.error(f"Unknown sensor: {sensor_name}")
            return None

        # Replace {baby_id} placeholder in endpoint
        endpoint = self.endpoint_map[sensor_name].format(baby_id=baby_id)
        url = self.base_url + endpoint

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(
                            f"Successfully fetched {sensor_name} for baby {baby_id}: {data}"
                        )
                        return data
                    else:
                        logger.warning(
                            f"Sensor {sensor_name} for baby {baby_id} returned status {response.status}"
                        )
                        return None

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching {sensor_name} for baby {baby_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {sensor_name} for baby {baby_id}: {e}")
            return None
