import aiohttp
import logging
from typing import Protocol, Optional, Dict, Any

logger = logging.getLogger(__name__)


# The abstraction - any class with this method can be used
class SensorDataSource(Protocol):
    async def get_sensor_data(self, sensor_name: str) -> Optional[Dict[str, Any]]:
        ...


class HttpSensorSource:

    def __init__(self, base_url: str, endpoint_map: Dict[str, str], timeout_seconds: int = 15):
        self.base_url = base_url
        self.endpoint_map = endpoint_map
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def get_sensor_data(self, sensor_name: str) -> Optional[Dict[str, Any]]:
        if sensor_name not in self.endpoint_map:
            logger.error(f"Unknown sensor: {sensor_name}")
            return None

        url = self.base_url + self.endpoint_map[sensor_name]

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"Successfully fetched data from {sensor_name}: {data}")
                        return data
                    else:
                        logger.warning(
                            f"Sensor {sensor_name} returned status {response.status}"
                        )
                        return None

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching {sensor_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {sensor_name}: {e}")
            return None

