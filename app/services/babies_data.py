import logging
from typing import List, Optional
from app.core.database import get_database
from app.db.models import Babies, SleepRealtimeData
from sqlalchemy import text

logger = logging.getLogger(__name__)


class BabyDataManager:
    """
    Manager class for baby-related database operations.
    Provides type-safe methods using Pydantic models.
    """

    def __init__(self):
        self.database = get_database()

    async def get_babies_list(self) -> List[Babies]:

        async with self.database.session() as session:
            result = await session.execute(
                text('SELECT * FROM "Nappi"."babies"'),
            )
            rows = result.mappings().all()
            return [Babies(**row) for row in rows]

    async def insert_sleep_realtime_data(
        self,
        baby_id: int,
        temp_celcius: Optional[float] = None,
        humidity: Optional[float] = None,
        noise_decibel: Optional[float] = None,
        heart_rate: Optional[float] = None,
        sleep_quality_score: Optional[int] = None
    ) -> Optional[SleepRealtimeData]:
        """
        Insert new sensor reading for a baby into sleep_realtime_data table.
        
        Args:
            baby_id: ID of the baby
            temp_celcius: Temperature in Celsius
            humidity: Humidity percentage
            noise_decibel: Noise level in decibels
            heart_rate: Heart rate in BPM
            sleep_quality_score: Sleep quality score (0-100)
            
        Returns:
            SleepRealtimeData object if successful, None otherwise
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."sleep_realtime_data" 
                        (baby_id, datetime, humidity, temp_celcius, noise_decibel, heart_rate, sleep_quality_score)
                        VALUES (:baby_id, NOW(), :humidity, :temp_celcius, :noise_decibel, :heart_rate, :sleep_quality_score)
                        RETURNING *
                    '''),
                    {
                        "baby_id": baby_id,
                        "humidity": humidity,
                        "temp_celcius": temp_celcius,
                        "noise_decibel": noise_decibel,
                        "heart_rate": heart_rate,
                        "sleep_quality_score": sleep_quality_score
                    }
                )
                await session.commit()
                row = result.mappings().first()
                if row:
                    return SleepRealtimeData(**row)
                return None
        except Exception as e:
            logger.error(f"Failed to insert sleep data for baby {baby_id}: {e}")
            return None

    async def set_baby_daily_summary(self, baby_id: int):
        """TODO: Implement daily summary calculation"""
        async with self.database.session() as session:
            pass

    async def set_baby_awaking_event(self, baby_id: int):
        """TODO: Implement awakening event recording"""
        async with self.database.session() as session:
            pass



