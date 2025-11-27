import asyncio
import logging
from typing import List, Optional, Dict, Any
from .data_miner import SensorDataSource

logger = logging.getLogger(__name__)


async def collect_sensor_data_task(
    data_source: SensorDataSource,
    sensor_names: List[str]
) -> List[Optional[Dict[str, Any]]]:

    logger.info("Starting sensor data collection task...")

    tasks = [
        asyncio.create_task(data_source.get_sensor_data(sensor))
        for sensor in sensor_names
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful = sum(1 for r in results if r is not None and not isinstance(r, Exception))
    logger.info(f"Sensor data collection complete: {successful}/{len(results)} successful")

    return results
