import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.core.database import get_database
from app.db.models import Babies, SleepRealtimeData, AwakeningEvents, Correlations, DailySummary, OptimalStats
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

    # ============================================
    # Optimal Stats Methods
    # ============================================

    async def get_all_daily_summaries(
        self,
        baby_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all daily summaries for a baby (all historical data).
        
        Args:
            baby_id: The ID of the baby
            
        Returns:
            List of daily summary dictionaries
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT id, baby_id, avg_humidity, avg_temp, avg_noise,
                               morning_awakes_sum, noon_awakes_sum, night_awakes_sum,
                               summary_date
                        FROM "Nappi"."daily_summary"
                        WHERE baby_id = :baby_id
                        ORDER BY summary_date ASC
                    '''),
                    {"baby_id": baby_id}
                )
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(
                f"Failed to get daily summaries for baby {baby_id}: {e}"
            )
            return []

    async def upsert_optimal_stats(
        self,
        baby_id: int,
        temperature: Optional[float] = None,
        humidity: Optional[float] = None,
        noise: Optional[float] = None,
        heart_rate: Optional[float] = None
    ) -> Optional[int]:
        """
        Insert or update optimal stats for a baby.
        
        If a record exists for the baby, update it. Otherwise, insert a new one.
        
        Args:
            baby_id: The ID of the baby
            temperature: Optimal temperature
            humidity: Optimal humidity
            noise: Optimal noise level
            heart_rate: Optimal heart rate
            
        Returns:
            The ID of the upserted record, or None if operation failed
        """
        try:
            async with self.database.session() as session:
                # Use PostgreSQL's INSERT ... ON CONFLICT for upsert
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."optimal_stats" 
                        (baby_id, temperature, humidity, noise, heart_rate)
                        VALUES (:baby_id, :temperature, :humidity, :noise, :heart_rate)
                        ON CONFLICT (baby_id) 
                        DO UPDATE SET 
                            temperature = EXCLUDED.temperature,
                            humidity = EXCLUDED.humidity,
                            noise = EXCLUDED.noise,
                            heart_rate = EXCLUDED.heart_rate
                        RETURNING id
                    '''),
                    {
                        "baby_id": baby_id,
                        "temperature": temperature,
                        "humidity": humidity,
                        "noise": noise,
                        "heart_rate": heart_rate
                    }
                )
                await session.commit()
                row = result.fetchone()
                if row:
                    stats_id = row[0]
                    logger.info(
                        f"Upserted optimal stats {stats_id} for baby {baby_id}: "
                        f"temp={temperature}, humidity={humidity}, noise={noise}"
                    )
                    return stats_id
                return None
        except Exception as e:
            logger.error(f"Failed to upsert optimal stats for baby {baby_id}: {e}")
            return None

    # ============================================
    # Statistics Methods
    # ============================================

    async def get_daily_summaries_range(
        self,
        baby_id: int,
        start_date: date_type,
        end_date: date_type
    ) -> List[Dict[str, Any]]:
        """
        Get daily summaries for a baby within a date range.
        
        Args:
            baby_id: The ID of the baby
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of daily summary dictionaries with sensor averages
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT summary_date, avg_humidity, avg_temp, avg_noise
                        FROM "Nappi"."daily_summary"
                        WHERE baby_id = :baby_id
                          AND summary_date >= :start_date
                          AND summary_date <= :end_date
                        ORDER BY summary_date ASC
                    '''),
                    {
                        "baby_id": baby_id,
                        "start_date": start_date,
                        "end_date": end_date
                    }
                )
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(
                f"Failed to get daily summaries range for baby {baby_id}: {e}"
            )
            return []

    async def get_sleep_sessions_for_month(
        self,
        baby_id: int,
        year: int,
        month: int
    ) -> List[Dict[str, Any]]:
        """
        Get all sleep sessions for a baby in a specific month.
        Extracts sleep_started_at and awakened_at from event_metadata.
        
        Args:
            baby_id: The ID of the baby
            year: Year (e.g., 2026)
            month: Month (1-12)
            
        Returns:
            List of dictionaries with sleep_started_at, awakened_at, duration_minutes
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT 
                            event_metadata->>'sleep_started_at' as sleep_started_at,
                            event_metadata->>'awakened_at' as awakened_at,
                            (event_metadata->>'sleep_duration_minutes')::float as duration_minutes
                        FROM "Nappi"."awakening_events"
                        WHERE baby_id = :baby_id
                          AND EXTRACT(YEAR FROM (event_metadata->>'awakened_at')::timestamp) = :year
                          AND EXTRACT(MONTH FROM (event_metadata->>'awakened_at')::timestamp) = :month
                        ORDER BY (event_metadata->>'sleep_started_at')::timestamp ASC
                    '''),
                    {
                        "baby_id": baby_id,
                        "year": year,
                        "month": month
                    }
                )
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(
                f"Failed to get sleep sessions for baby {baby_id} ({year}-{month}): {e}"
            )
            return []

    async def get_sleep_sessions_for_range(
        self,
        baby_id: int,
        start_date: date_type,
        end_date: date_type
    ) -> List[Dict[str, Any]]:
        """
        Get all sleep sessions for a baby within a date range.
        Used for calculating daily sleep totals.
        
        Args:
            baby_id: The ID of the baby
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of dictionaries with awakened_at date and duration_minutes
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT 
                            DATE((event_metadata->>'awakened_at')::timestamp) as session_date,
                            (event_metadata->>'sleep_duration_minutes')::float as duration_minutes
                        FROM "Nappi"."awakening_events"
                        WHERE baby_id = :baby_id
                          AND DATE((event_metadata->>'awakened_at')::timestamp) >= :start_date
                          AND DATE((event_metadata->>'awakened_at')::timestamp) <= :end_date
                        ORDER BY (event_metadata->>'awakened_at')::timestamp ASC
                    '''),
                    {
                        "baby_id": baby_id,
                        "start_date": start_date,
                        "end_date": end_date
                    }
                )
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(
                f"Failed to get sleep sessions for baby {baby_id} ({start_date} to {end_date}): {e}"
            )
            return []

    async def baby_exists(self, baby_id: int) -> bool:
        """
        Check if a baby exists in the database.
        
        Args:
            baby_id: The ID of the baby
            
        Returns:
            True if baby exists, False otherwise
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('SELECT 1 FROM "Nappi"."babies" WHERE id = :baby_id'),
                    {"baby_id": baby_id}
                )
                return result.first() is not None
        except Exception as e:
            logger.error(f"Failed to check if baby {baby_id} exists: {e}")
            return False

    async def get_awakening_event_by_id(
        self,
        event_id: int,
        baby_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific awakening event by ID.
        
        Args:
            event_id: The ID of the awakening event
            baby_id: The ID of the baby (for validation)
            
        Returns:
            Dictionary with event data or None if not found
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT 
                            id,
                            baby_id,
                            (event_metadata->>'sleep_started_at')::timestamp as sleep_started_at,
                            (event_metadata->>'awakened_at')::timestamp as awakened_at,
                            (event_metadata->>'sleep_duration_minutes')::float as sleep_duration_minutes,
                            event_metadata
                        FROM "Nappi"."awakening_events"
                        WHERE id = :event_id AND baby_id = :baby_id
                    '''),
                    {"event_id": event_id, "baby_id": baby_id}
                )
                row = result.mappings().first()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get awakening event {event_id}: {e}")
            return None

    async def get_latest_awakening_event(
        self,
        baby_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent awakening event for a baby.
        
        Args:
            baby_id: The ID of the baby
            
        Returns:
            Dictionary with event data or None if no events found
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT 
                            id,
                            baby_id,
                            (event_metadata->>'sleep_started_at')::timestamp as sleep_started_at,
                            (event_metadata->>'awakened_at')::timestamp as awakened_at,
                            (event_metadata->>'sleep_duration_minutes')::float as sleep_duration_minutes,
                            event_metadata
                        FROM "Nappi"."awakening_events"
                        WHERE baby_id = :baby_id
                        ORDER BY (event_metadata->>'awakened_at')::timestamp DESC
                        LIMIT 1
                    '''),
                    {"baby_id": baby_id}
                )
                row = result.mappings().first()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get latest awakening event for baby {baby_id}: {e}")
            return None

    async def update_awakening_event_insight(
        self,
        event_id: int,
        insight: str
    ) -> bool:
        """
        Update an awakening event's event_metadata with AI-generated insight.
        
        Args:
            event_id: The ID of the awakening event
            insight: The AI-generated insight text
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import json
            async with self.database.session() as session:
                # Get current event_metadata, add insight, and update
                result = await session.execute(
                    text('''
                        SELECT event_metadata FROM "Nappi"."awakening_events"
                        WHERE id = :event_id
                    '''),
                    {"event_id": event_id}
                )
                row = result.first()
                
                if row:
                    current_metadata = row[0] or {}
                    current_metadata["ai_insight"] = insight
                    
                    await session.execute(
                        text('''
                            UPDATE "Nappi"."awakening_events"
                            SET event_metadata = :metadata
                            WHERE id = :event_id
                        '''),
                        {"event_id": event_id, "metadata": json.dumps(current_metadata)}
                    )
                    await session.commit()
                    logger.info(f"Updated awakening event {event_id} with AI insight")
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to update awakening event {event_id} with insight: {e}")
            return False
