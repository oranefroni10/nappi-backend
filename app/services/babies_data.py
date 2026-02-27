"""Baby-related database operations."""

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.core.database import get_database
from app.db.models import Babies, SleepRealtimeData, AwakeningEvents, Correlations, DailySummary, OptimalStats, BabyNote
from datetime import date as date_type
from sqlalchemy import text

logger = logging.getLogger(__name__)


class BabyDataManager:
    def __init__(self):
        self.database = get_database()

    # Used by: sensor_events.py, endpoints.py, tasks.py, daily_summary.py, optimal_stats.py, correlation_analyzer.py
    async def get_babies_list(self) -> List[Babies]:
        async with self.database.session() as session:
            result = await session.execute(
                text('SELECT * FROM "Nappi"."babies"'),
            )
            rows = result.mappings().all()
            return [Babies(**row) for row in rows]

    # Used by: tasks.py (sensor polling)
    async def insert_sleep_realtime_data(
            self,
            baby_id: int,
            temp_celcius: Optional[float] = None,
            humidity: Optional[float] = None,
            noise_decibel: Optional[float] = None,
    ) -> Optional[SleepRealtimeData]:
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."sleep_realtime_data"
                        (baby_id, datetime, humidity, temp_celcius, noise_decibel)
                        VALUES (:baby_id, NOW(), :humidity, :temp_celcius, :noise_decibel)
                        RETURNING *
                    '''),
                    {
                        "baby_id": baby_id,
                        "humidity": humidity,
                        "temp_celcius": temp_celcius,
                        "noise_decibel": noise_decibel,
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

    # Used by: sensor_events.py (sleep-end endpoint)
    async def set_baby_awaking_event(
            self,
            baby_id: int,
            event_metadata: Dict[str, Any]
    ) -> Optional[int]:
        """Record an awakening event for a baby."""
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

    # Used by: sensor_events.py, endpoints.py, stats.py, chat_service.py
    async def get_last_sensor_readings(
            self,
            baby_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent sensor readings for a baby."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT datetime, humidity, temp_celcius, noise_decibel
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

    # Used by: correlation_analyzer.py, daily_summary.py
    async def get_sensor_data_range(
            self,
            baby_id: int,
            start_time: datetime,
            end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get sensor readings for a baby within a time range."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT datetime, humidity, temp_celcius, noise_decibel
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

    # Used by: correlation_analyzer.py
    async def insert_correlation(
            self,
            baby_id: int,
            correlation_time: datetime,
            parameters: Dict[str, Any],
            extra_data: Optional[str] = None
    ) -> Optional[int]:
        """Insert a correlation record for a baby's awakening."""
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

    # Used by: daily_summary.py, correlation_analyzer.py
    async def get_awakening_events_for_period(
            self,
            baby_id: int,
            start_time: datetime,
            end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get awakening events for a baby within a time range."""
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

    # Used by: daily_summary.py
    async def insert_daily_summary(
            self,
            baby_id: int,
            summary_date: date_type,
            avg_humidity: Optional[float] = None,
            avg_temp: Optional[float] = None,
            avg_noise: Optional[float] = None,
            morning_awakes_sum: Optional[int] = None,
            noon_awakes_sum: Optional[int] = None,
            night_awakes_sum: Optional[int] = None
    ) -> Optional[int]:
        """Insert a daily summary record for a baby."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."daily_summary"
                        (baby_id, summary_date, avg_humidity, avg_temp, avg_noise,
                         morning_awakes_sum, noon_awakes_sum, night_awakes_sum)
                        VALUES (:baby_id, :summary_date, :avg_humidity, :avg_temp, :avg_noise,
                                :morning_awakes_sum, :noon_awakes_sum, :night_awakes_sum)
                        RETURNING id
                    '''),
                    {
                        "baby_id": baby_id,
                        "summary_date": summary_date,
                        "avg_humidity": avg_humidity,
                        "avg_temp": avg_temp,
                        "avg_noise": avg_noise,
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

    # Used by: daily_summary.py
    async def delete_sleep_data_for_period(
            self,
            baby_id: int,
            start_time: datetime,
            end_time: datetime
    ) -> int:
        """Delete sleep realtime data for a baby within a time range."""
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

    # Used by: optimal_stats.py
    async def get_all_daily_summaries(
            self,
            baby_id: int
    ) -> List[Dict[str, Any]]:
        """Get all daily summaries for a baby."""
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

    # Used by: optimal_stats.py
    async def upsert_optimal_stats(
            self,
            baby_id: int,
            temperature: Optional[float] = None,
            humidity: Optional[float] = None,
            noise: Optional[float] = None
    ) -> Optional[int]:
        """Insert or update optimal stats for a baby."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."optimal_stats"
                        (baby_id, temperature, humidity, noise)
                        VALUES (:baby_id, :temperature, :humidity, :noise)
                        ON CONFLICT (baby_id)
                        DO UPDATE SET
                            temperature = EXCLUDED.temperature,
                            humidity = EXCLUDED.humidity,
                            noise = EXCLUDED.noise
                        RETURNING id
                    '''),
                    {
                        "baby_id": baby_id,
                        "temperature": temperature,
                        "humidity": humidity,
                        "noise": noise
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

    # Used by: stats.py, trend_analyzer.py, chat_service.py
    async def get_daily_summaries_range(
            self,
            baby_id: int,
            start_date: date_type,
            end_date: date_type
    ) -> List[Dict[str, Any]]:
        """Get daily summaries for a baby within a date range."""
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

    # Used by: stats.py, chat_service.py, schedule_predictor.py
    async def get_sleep_sessions_for_month(
            self,
            baby_id: int,
            year: int,
            month: int
    ) -> List[Dict[str, Any]]:
        """Get sleep sessions for a baby in a specific month."""
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

    # Used by: stats.py, trend_analyzer.py
    async def get_sleep_sessions_for_range(
            self,
            baby_id: int,
            start_date: date_type,
            end_date: date_type
    ) -> List[Dict[str, Any]]:
        """Get sleep sessions for a baby within a date range."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT
                            DATE((event_metadata->>'awakened_at')::timestamp) as session_date,
                            (event_metadata->>'sleep_duration_minutes')::float as duration_minutes,
                            event_metadata->>'sleep_started_at' as sleep_started_at,
                            event_metadata->>'awakened_at' as awakened_at
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

    # Used by: stats.py
    async def baby_exists(self, baby_id: int) -> bool:
        """Check if a baby exists in the database."""
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

    # Used by: stats.py
    async def get_awakening_event_by_id(
            self,
            event_id: int,
            baby_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a specific awakening event by ID."""
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

    # Used by: stats.py, schedule_predictor.py
    async def get_latest_awakening_event(
            self,
            baby_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent awakening event for a baby."""
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

    # Used by: sensor_events.py (sleep-end - attaches AI insight)
    async def update_awakening_event_insight(
            self,
            event_id: int,
            insight: str
    ) -> bool:
        """Update an awakening event's event_metadata with AI-generated insight."""
        try:
            import json
            async with self.database.session() as session:
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

    # Used by: stats.py, chat_service.py
    async def get_optimal_stats(self, baby_id: int) -> Optional[Dict[str, Any]]:
        """Get the optimal sleep conditions for a baby."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT temperature, humidity, noise
                        FROM "Nappi"."optimal_stats"
                        WHERE baby_id = :baby_id
                        LIMIT 1
                    '''),
                    {"baby_id": baby_id}
                )
                row = result.mappings().first()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get optimal stats for baby {baby_id}: {e}")
            return None

    # Used by: babies.py, correlation_analyzer.py, self.get_baby_notes_formatted()
    async def get_baby_notes(self, baby_id: int) -> List[BabyNote]:
        """Get all notes for a baby."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT id, baby_id, title, content, created_at, updated_at
                        FROM "Nappi"."baby_notes"
                        WHERE baby_id = :baby_id
                        ORDER BY created_at DESC
                    '''),
                    {"baby_id": baby_id}
                )
                rows = result.mappings().all()
                return [BabyNote(**row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get notes for baby {baby_id}: {e}")
            return []

    # Used by: babies.py (create note endpoint)
    async def create_baby_note(
            self,
            baby_id: int,
            title: str,
            content: str
    ) -> Optional[BabyNote]:
        """Create a new note for a baby."""
        try:
            truncated_title = title[:200] if title else "Untitled"

            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."baby_notes" (baby_id, title, content, created_at, updated_at)
                        VALUES (:baby_id, :title, :content, NOW(), NOW())
                        RETURNING id, baby_id, title, content, created_at, updated_at
                    '''),
                    {"baby_id": baby_id, "title": truncated_title, "content": content}
                )
                await session.commit()
                row = result.mappings().first()
                if row:
                    logger.info(f"Created note '{truncated_title}' for baby {baby_id}")
                    return BabyNote(**row)
                return None
        except Exception as e:
            logger.error(f"Failed to create note for baby {baby_id}: {e}")
            return None

    # Used by: babies.py (update note endpoint)
    async def update_baby_note(
            self,
            note_id: int,
            baby_id: int,
            title: str,
            content: str
    ) -> Optional[BabyNote]:
        """Update an existing note."""
        try:
            truncated_title = title[:200] if title else "Untitled"

            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        UPDATE "Nappi"."baby_notes"
                        SET title = :title, content = :content, updated_at = NOW()
                        WHERE id = :note_id AND baby_id = :baby_id
                        RETURNING id, baby_id, title, content, created_at, updated_at
                    '''),
                    {"note_id": note_id, "baby_id": baby_id, "title": truncated_title, "content": content}
                )
                await session.commit()
                row = result.mappings().first()
                if row:
                    logger.info(f"Updated note {note_id} for baby {baby_id}")
                    return BabyNote(**row)
                return None
        except Exception as e:
            logger.error(f"Failed to update note {note_id} for baby {baby_id}: {e}")
            return None

    # Used by: babies.py (delete note endpoint)
    async def delete_baby_note(self, note_id: int, baby_id: int) -> bool:
        """Delete a note."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        DELETE FROM "Nappi"."baby_notes"
                        WHERE id = :note_id AND baby_id = :baby_id
                        RETURNING id
                    '''),
                    {"note_id": note_id, "baby_id": baby_id}
                )
                await session.commit()
                deleted = result.first() is not None
                if deleted:
                    logger.info(f"Deleted note {note_id} for baby {baby_id}")
                return deleted
        except Exception as e:
            logger.error(f"Failed to delete note {note_id} for baby {baby_id}: {e}")
            return False

    # Used by: chat_service.py (AI chat context)
    async def get_baby_notes_formatted(self, baby_id: int) -> str:
        """Get all notes for a baby formatted as string for AI context."""
        notes = await self.get_baby_notes(baby_id)
        if not notes:
            return ""

        formatted = []
        for note in notes:
            formatted.append(f"- [{note.title}]: {note.content}")

        return "\n".join(formatted)

    # Used by: chat.py, babies.py
    async def validate_baby_ownership(self, user_id: int, baby_id: int) -> bool:
        """Validate that a user owns a specific baby."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT 1 FROM "Nappi"."users"
                        WHERE id = :user_id AND baby_id = :baby_id
                    '''),
                    {"user_id": user_id, "baby_id": baby_id}
                )
                return result.first() is not None
        except Exception as e:
            logger.error(f"Failed to validate baby ownership for user {user_id}, baby {baby_id}: {e}")
            return False

    # Used by: chat_service.py, stats.py, trend_analyzer.py, schedule_predictor.py
    async def get_baby_by_id(self, baby_id: int) -> Optional[Babies]:
        """Get a baby by ID."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('SELECT * FROM "Nappi"."babies" WHERE id = :baby_id'),
                    {"baby_id": baby_id}
                )
                row = result.mappings().first()
                if row:
                    return Babies(**row)
                return None
        except Exception as e:
            logger.error(f"Failed to get baby {baby_id}: {e}")
            return None

    # Used by: chat_service.py
    async def get_recent_awakenings_with_insights(
            self,
            baby_id: int,
            limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get recent awakening events with AI insights for chat context."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT
                            id,
                            (event_metadata->>'awakened_at')::timestamp as awakened_at,
                            (event_metadata->>'sleep_duration_minutes')::float as sleep_duration_minutes,
                            event_metadata->>'ai_insight' as ai_insight,
                            event_metadata->>'last_sensor_readings' as last_sensor_readings
                        FROM "Nappi"."awakening_events"
                        WHERE baby_id = :baby_id
                        ORDER BY (event_metadata->>'awakened_at')::timestamp DESC
                        LIMIT :limit
                    '''),
                    {"baby_id": baby_id, "limit": limit}
                )
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get recent awakenings for baby {baby_id}: {e}")
            return []

    # Used by: chat_service.py
    async def get_recent_correlations(
            self,
            baby_id: int,
            limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get recent correlation analyses for chat context."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT
                            id,
                            time,
                            parameters,
                            extra_data
                        FROM "Nappi"."correlations"
                        WHERE baby_id = :baby_id
                        ORDER BY time DESC
                        LIMIT :limit
                    '''),
                    {"baby_id": baby_id, "limit": limit}
                )
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get recent correlations for baby {baby_id}: {e}")
            return []
