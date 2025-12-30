import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.core.database import get_database
from app.db.models import Babies, SleepRealtimeData, AwakeningEvents, Correlations, DailySummary
from datetime import date as date_type
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

    async def set_baby_awaking_event(
        self, 
        baby_id: int, 
        event_metadata: Dict[str, Any]
    ) -> Optional[int]:
        """
        Record an awakening event for a baby.
        
        Args:
            baby_id: The ID of the baby who woke up
            event_metadata: Dictionary containing event details:
                - sleep_started_at: ISO timestamp of when sleep began
                - awakened_at: ISO timestamp of when baby woke up
                - sleep_duration_minutes: Duration of sleep in minutes
                - last_sensor_readings: Dict of last sensor values before wake
        
        Returns:
            The ID of the created event, or None if insertion failed
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."awakening_events" 
                        (baby_id, event_metadata)
                        VALUES (:baby_id, CAST(:event_metadata AS jsonb))
                        RETURNING id
                    '''),
                    {
                        "baby_id": baby_id,
                        "event_metadata": json.dumps(event_metadata)
                    }
                )
                await session.commit()
                row = result.fetchone()
                if row:
                    event_id = row[0]
                    logger.info(f"Created awakening event {event_id} for baby {baby_id}")
                    return event_id
                return None
        except Exception as e:
            logger.error(f"Failed to insert awakening event for baby {baby_id}: {e}")
            return None

    async def get_last_sensor_readings(
        self, 
        baby_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent sensor readings for a baby.
        
        Args:
            baby_id: The ID of the baby
            
        Returns:
            Dictionary with the last sensor readings, or None if no data
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT datetime, humidity, temp_celcius, noise_decibel, heart_rate
                        FROM "Nappi"."sleep_realtime_data"
                        WHERE baby_id = :baby_id
                        ORDER BY datetime DESC
                        LIMIT 1
                    '''),
                    {"baby_id": baby_id}
                )
                row = result.mappings().first()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get last sensor readings for baby {baby_id}: {e}")
            return None

    async def get_sensor_data_range(
        self,
        baby_id: int,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get sensor readings for a baby within a specific time range.
        
        Args:
            baby_id: The ID of the baby
            start_time: Start of the time window
            end_time: End of the time window
            
        Returns:
            List of sensor reading dictionaries ordered by datetime
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT datetime, humidity, temp_celcius, noise_decibel, heart_rate
                        FROM "Nappi"."sleep_realtime_data"
                        WHERE baby_id = :baby_id
                          AND datetime >= :start_time
                          AND datetime <= :end_time
                        ORDER BY datetime ASC
                    '''),
                    {
                        "baby_id": baby_id,
                        "start_time": start_time,
                        "end_time": end_time
                    }
                )
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(
                f"Failed to get sensor data range for baby {baby_id}: {e}"
            )
            return []

    async def insert_correlation(
        self,
        baby_id: int,
        correlation_time: datetime,
        parameters: Dict[str, Any],
        extra_data: Optional[str] = None
    ) -> Optional[int]:
        """
        Insert a correlation record for a baby's awakening.
        
        Args:
            baby_id: The ID of the baby
            correlation_time: The date/time of the correlation (awakening time)
            parameters: Dictionary of sensor parameters that changed significantly
            extra_data: Optional AI-generated insights
            
        Returns:
            The ID of the created correlation, or None if insertion failed
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."correlations" 
                        (baby_id, time, parameters, extra_data)
                        VALUES (:baby_id, :correlation_time, CAST(:parameters AS jsonb), :extra_data)
                        RETURNING id
                    '''),
                    {
                        "baby_id": baby_id,
                        "correlation_time": correlation_time.date(),
                        "parameters": json.dumps(parameters),
                        "extra_data": extra_data
                    }
                )
                await session.commit()
                row = result.fetchone()
                if row:
                    correlation_id = row[0]
                    logger.info(
                        f"Created correlation {correlation_id} for baby {baby_id}"
                    )
                    return correlation_id
                return None
        except Exception as e:
            logger.error(f"Failed to insert correlation for baby {baby_id}: {e}")
            return None

    # ============================================
    # Daily Summary Methods
    # ============================================

    async def get_awakening_events_for_period(
        self,
        baby_id: int,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get awakening events for a baby within a specific time range.
        
        Args:
            baby_id: The ID of the baby
            start_time: Start of the time window
            end_time: End of the time window
            
        Returns:
            List of awakening event dictionaries
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT id, baby_id, event_metadata
                        FROM "Nappi"."awakening_events"
                        WHERE baby_id = :baby_id
                          AND (event_metadata->>'awakened_at')::timestamp >= :start_time
                          AND (event_metadata->>'awakened_at')::timestamp <= :end_time
                        ORDER BY (event_metadata->>'awakened_at')::timestamp ASC
                    '''),
                    {
                        "baby_id": baby_id,
                        "start_time": start_time,
                        "end_time": end_time
                    }
                )
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(
                f"Failed to get awakening events for baby {baby_id}: {e}"
            )
            return []

    async def insert_daily_summary(
        self,
        baby_id: int,
        summary_date: date_type,
        avg_humidity: Optional[float] = None,
        avg_temp: Optional[float] = None,
        avg_noise: Optional[float] = None,
        anomalies: Optional[Dict[str, Any]] = None,
        morning_awakes_sum: Optional[int] = None,
        noon_awakes_sum: Optional[int] = None,
        night_awakes_sum: Optional[int] = None
    ) -> Optional[int]:
        """
        Insert a daily summary record for a baby.
        
        Args:
            baby_id: The ID of the baby
            summary_date: The date of the summary
            avg_humidity: Average humidity for the day
            avg_temp: Average temperature for the day
            avg_noise: Average noise level for the day
            anomalies: Dictionary of detected anomalies
            morning_awakes_sum: Count of awakenings during morning (6am-12pm)
            noon_awakes_sum: Count of awakenings during noon (12pm-6pm)
            night_awakes_sum: Count of awakenings during night (6pm-6am)
            
        Returns:
            The ID of the created summary, or None if insertion failed
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."daily_summary" 
                        (baby_id, summary_date, avg_humidity, avg_temp, avg_noise, 
                         anomalies, morning_awakes_sum, noon_awakes_sum, night_awakes_sum)
                        VALUES (:baby_id, :summary_date, :avg_humidity, :avg_temp, :avg_noise,
                                CAST(:anomalies AS jsonb), :morning_awakes_sum, :noon_awakes_sum, :night_awakes_sum)
                        RETURNING id
                    '''),
                    {
                        "baby_id": baby_id,
                        "summary_date": summary_date,
                        "avg_humidity": avg_humidity,
                        "avg_temp": avg_temp,
                        "avg_noise": avg_noise,
                        "anomalies": json.dumps(anomalies) if anomalies else None,
                        "morning_awakes_sum": morning_awakes_sum,
                        "noon_awakes_sum": noon_awakes_sum,
                        "night_awakes_sum": night_awakes_sum
                    }
                )
                await session.commit()
                row = result.fetchone()
                if row:
                    summary_id = row[0]
                    logger.info(
                        f"Created daily summary {summary_id} for baby {baby_id} on {summary_date}"
                    )
                    return summary_id
                return None
        except Exception as e:
            logger.error(f"Failed to insert daily summary for baby {baby_id}: {e}")
            return None

    async def delete_sleep_data_for_period(
        self,
        baby_id: int,
        start_time: datetime,
        end_time: datetime
    ) -> int:
        """
        Delete sleep realtime data for a baby within a specific time range.
        
        Args:
            baby_id: The ID of the baby
            start_time: Start of the time window
            end_time: End of the time window
            
        Returns:
            Number of rows deleted
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        DELETE FROM "Nappi"."sleep_realtime_data"
                        WHERE baby_id = :baby_id
                          AND datetime >= :start_time
                          AND datetime <= :end_time
                    '''),
                    {
                        "baby_id": baby_id,
                        "start_time": start_time,
                        "end_time": end_time
                    }
                )
                await session.commit()
                deleted_count = result.rowcount
                logger.info(
                    f"Deleted {deleted_count} sleep data rows for baby {baby_id} "
                    f"between {start_time} and {end_time}"
                )
                return deleted_count
        except Exception as e:
            logger.error(
                f"Failed to delete sleep data for baby {baby_id}: {e}"
            )
            return 0



