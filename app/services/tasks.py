"""Scheduled task — collects sensor data for sleeping babies and checks alert thresholds."""

import asyncio
import logging
from typing import Dict, Any, List
from .data_miner import HttpSensorSource
from .babies_data import BabyDataManager
from .sleep_state import get_sleep_state_manager
from .alert_service import get_alert_service
from app.core.utils import SENSOR_TO_ENDPOINT_MAP, SENSOR_TO_DB_COLUMN_MAP
from app.db.models import Babies

logger = logging.getLogger(__name__)


# Used by: scheduler.py — called every SENSOR_POLL_INTERVAL_SECONDS
async def collect_and_store_baby_sensor_data_task(
    data_source: HttpSensorSource
) -> Dict[str, Any]:
    """Collect sensor data only for sleeping babies."""
    logger.debug("Starting baby sensor data collection task...")
    
    baby_manager = BabyDataManager()
    sleep_state = get_sleep_state_manager()
    
    try:
        sleeping_baby_ids = await sleep_state.get_sleeping_babies()
        
        if not sleeping_baby_ids:
            logger.debug("No babies currently sleeping - skipping data collection")
            return {
                "success": 0, 
                "failed": 0, 
                "total": 0, 
                "message": "No babies currently sleeping"
            }
        
        all_babies = await baby_manager.get_babies_list()
        sleeping_babies: List[Babies] = [
            baby for baby in all_babies if baby.id in sleeping_baby_ids
        ]
        
        if not sleeping_babies:
            logger.warning(
                f"Sleeping baby IDs {sleeping_baby_ids} not found in database"
            )
            return {
                "success": 0, 
                "failed": 0, 
                "total": 0, 
                "message": "Sleeping babies not found in database"
            }
        
        logger.info(f"Collecting sensor data for {len(sleeping_babies)} sleeping baby/babies")
        
        baby_tasks = [
            asyncio.create_task(_process_single_baby(baby, data_source, baby_manager))
            for baby in sleeping_babies
        ]
        
        results = await asyncio.gather(*baby_tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        failed_count = sum(1 for r in results if r is not True)
        
        summary = {
            "success": success_count,
            "failed": failed_count,
            "total": len(sleeping_babies)
        }
        
        logger.info(
            f"Sensor data collection complete: {success_count}/{len(sleeping_babies)} successful, "
            f"{failed_count} failed"
        )
        return summary
        
    except Exception as e:
        logger.error(f"Fatal error in sensor data collection task: {e}", exc_info=True)
        return {"success": 0, "failed": 0, "total": 0, "error": str(e)}


# Used by: collect_and_store_baby_sensor_data_task() — processes one baby in parallel
async def _process_single_baby(
    baby: Babies,
    data_source: HttpSensorSource,
    baby_manager: BabyDataManager
) -> bool:

    try:
        logger.debug(f"Collecting sensor data for baby {baby.id} ({baby.first_name})")
        
        sensor_names = list(SENSOR_TO_ENDPOINT_MAP.keys())
        sensor_tasks = [
            asyncio.create_task(data_source.get_sensor_data(sensor, baby.id))
            for sensor in sensor_names
        ]
        
        sensor_results = await asyncio.gather(*sensor_tasks, return_exceptions=True)
        
        sensor_data = {}
        for sensor_name, result in zip(sensor_names, sensor_results):
            if result and not isinstance(result, Exception):
                db_column = SENSOR_TO_DB_COLUMN_MAP.get(sensor_name)
                if db_column and isinstance(result, dict) and "value" in result:
                    sensor_data[db_column] = result["value"]
                else:
                    logger.warning(
                        f"Invalid response format for {sensor_name} (baby {baby.id}): {result}"
                    )
            else:
                logger.warning(
                    f"Failed to get {sensor_name} for baby {baby.id}: "
                    f"{result if isinstance(result, Exception) else 'No data'}"
                )
        
        if sensor_data:
            inserted = await baby_manager.insert_sleep_realtime_data(
                baby_id=baby.id,
                **sensor_data
            )
            
            if inserted:
                logger.info(
                    f"Stored sensor data for baby {baby.id} ({baby.first_name}): "
                    f"{len(sensor_data)}/{len(sensor_names)} sensors"
                )
                
                try:
                    alert_service = get_alert_service()
                    await alert_service.check_thresholds(
                        baby_id=baby.id,
                        temperature=sensor_data.get("temp_celcius"),
                        humidity=sensor_data.get("humidity"),
                        noise_db=sensor_data.get("noise_decibel")
                    )
                except Exception as e:
                    logger.warning(f"Failed to check thresholds for baby {baby.id}: {e}")
                
                return True
            else:
                logger.error(f"Failed to store data in DB for baby {baby.id}")
                return False
        else:
            logger.warning(
                f"No sensor data collected for baby {baby.id} - all sensors failed"
            )
            return False
            
    except Exception as e:
        logger.error(f"Error processing baby {baby.id}: {e}", exc_info=True)
        return False
