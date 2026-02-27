"""Alert service: creates, stores, broadcasts alerts via SSE and push."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from app.core.database import get_database
from app.core.constants import (
    ALERT_COOLDOWN_MINUTES, ALERTS_DEFAULT_PAGE_SIZE,
    TEMP_ALERT_HIGH_C, TEMP_ALERT_LOW_C,
    HUMIDITY_ALERT_HIGH_PCT, HUMIDITY_ALERT_LOW_PCT,
    NOISE_ALERT_HIGH_DB,
)
from sqlalchemy import text

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    AWAKENING = "awakening"
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    NOISE = "noise"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"


@dataclass
class Alert:
    id: Optional[int]
    baby_id: int
    user_id: int
    type: str
    title: str
    message: str
    severity: str = "info"
    metadata: Optional[Dict[str, Any]] = None
    read: bool = False
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if data["created_at"]:
            data["created_at"] = data["created_at"].isoformat()
        return data


TEMP_HIGH = TEMP_ALERT_HIGH_C
TEMP_LOW = TEMP_ALERT_LOW_C
HUMIDITY_HIGH = HUMIDITY_ALERT_HIGH_PCT
HUMIDITY_LOW = HUMIDITY_ALERT_LOW_PCT
NOISE_HIGH = NOISE_ALERT_HIGH_DB


class SSEManager:
    def __init__(self):
        self._queues: Dict[int, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    # Used by: alerts.py (SSE stream endpoint - client connects)
    async def subscribe(self, user_id: int) -> asyncio.Queue:
        """Subscribe a client to receive alerts."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            if user_id not in self._queues:
                self._queues[user_id] = set()
            self._queues[user_id].add(queue)
            logger.info(f"SSE client subscribed for user {user_id}")
        return queue

    # Used by: alerts.py (SSE stream endpoint - client disconnects)
    async def unsubscribe(self, user_id: int, queue: asyncio.Queue):
        """Unsubscribe a client."""
        async with self._lock:
            if user_id in self._queues:
                self._queues[user_id].discard(queue)
                if not self._queues[user_id]:
                    del self._queues[user_id]
            logger.info(f"SSE client unsubscribed for user {user_id}")

    # Used by: AlertService.create_alert()
    async def broadcast(self, user_id: int, alert: Alert):
        """Broadcast an alert to all connected clients for a user."""
        async with self._lock:
            queues = self._queues.get(user_id, set())
            for queue in queues:
                try:
                    await queue.put(alert)
                except Exception as e:
                    logger.error(f"Failed to broadcast alert to queue: {e}")

    # Used by: (internal utility)
    def get_connected_count(self, user_id: int) -> int:
        """Get number of connected clients for a user."""
        return len(self._queues.get(user_id, set()))


_sse_manager: Optional[SSEManager] = None


# Used by: alerts.py (SSE stream endpoint), AlertService.__init__()
def get_sse_manager() -> SSEManager:
    """Get the SSE manager singleton."""
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEManager()
    return _sse_manager


class AlertService:
    def __init__(self):
        self.database = get_database()
        self.sse_manager = get_sse_manager()
        self._alert_cooldowns: Dict[Tuple[int, str], datetime] = {}

    # Used by: self.check_thresholds()
    def _is_alert_on_cooldown(self, baby_id: int, alert_type: str) -> bool:
        """Check if an alert type is on cooldown for a baby."""
        key = (baby_id, alert_type)
        cooldown_until = self._alert_cooldowns.get(key)
        if cooldown_until and datetime.utcnow() < cooldown_until:
            return True
        return False

    # Used by: self.check_thresholds()
    def _set_alert_cooldown(self, baby_id: int, alert_type: str) -> None:
        """Set cooldown for an alert type for a baby."""
        key = (baby_id, alert_type)
        self._alert_cooldowns[key] = datetime.utcnow() + timedelta(minutes=ALERT_COOLDOWN_MINUTES)

    # Used by: self.check_thresholds(), self.create_awakening_alert()
    async def get_user_id_for_baby(self, baby_id: int) -> Optional[int]:
        """Get the user_id who owns this baby."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('SELECT id FROM "Nappi"."users" WHERE baby_id = :baby_id LIMIT 1'),
                    {"baby_id": baby_id}
                )
                row = result.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Failed to get user_id for baby {baby_id}: {e}")
            return None

    # Used by: self.check_thresholds(), self.create_awakening_alert()
    async def create_alert(
        self,
        baby_id: int,
        user_id: int,
        alert_type: str,
        title: str,
        message: str,
        severity: str = "info",
        metadata: Optional[Dict[str, Any]] = None,
        send_push: bool = True
    ) -> Optional[Alert]:
        """Create and store alert, broadcast via SSE, optionally send push."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        INSERT INTO "Nappi"."alerts"
                        (baby_id, user_id, type, title, message, severity, metadata, read, created_at)
                        VALUES (:baby_id, :user_id, :type, :title, :message, :severity,
                                CAST(:metadata AS jsonb), FALSE, NOW())
                        RETURNING id, created_at
                    '''),
                    {
                        "baby_id": baby_id,
                        "user_id": user_id,
                        "type": alert_type,
                        "title": title,
                        "message": message,
                        "severity": severity,
                        "metadata": json.dumps(metadata) if metadata else None
                    }
                )
                await session.commit()
                row = result.fetchone()

                if row:
                    alert = Alert(
                        id=row[0],
                        baby_id=baby_id,
                        user_id=user_id,
                        type=alert_type,
                        title=title,
                        message=message,
                        severity=severity,
                        metadata=metadata,
                        read=False,
                        created_at=row[1]
                    )

                    logger.info(f"Created alert {alert.id} for user {user_id}: {title}")

                    await self.sse_manager.broadcast(user_id, alert)

                    if send_push:
                        await self._send_push_notification(user_id, alert)

                    return alert
                return None

        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
            return None

    # Used by: alerts.py (GET alerts list endpoint)
    async def get_alerts_for_user(
        self,
        user_id: int,
        limit: int = ALERTS_DEFAULT_PAGE_SIZE,
        offset: int = 0,
        unread_only: bool = False
    ) -> List[Alert]:
        """Get paginated alerts for a user."""
        try:
            async with self.database.session() as session:
                query = '''
                    SELECT id, baby_id, user_id, type, title, message,
                           severity, metadata, read, created_at
                    FROM "Nappi"."alerts"
                    WHERE user_id = :user_id
                '''
                if unread_only:
                    query += ' AND read = FALSE'
                query += ' ORDER BY created_at DESC LIMIT :limit OFFSET :offset'

                result = await session.execute(
                    text(query),
                    {"user_id": user_id, "limit": limit, "offset": offset}
                )
                rows = result.mappings().all()

                return [
                    Alert(
                        id=row["id"],
                        baby_id=row["baby_id"],
                        user_id=row["user_id"],
                        type=row["type"],
                        title=row["title"],
                        message=row["message"],
                        severity=row["severity"],
                        metadata=row["metadata"],
                        read=row["read"],
                        created_at=row["created_at"]
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to get alerts for user {user_id}: {e}")
            return []

    # Used by: alerts.py (GET unread count endpoint)
    async def get_unread_count(self, user_id: int) -> int:
        """Get the count of unread alerts for a user."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT COUNT(*) FROM "Nappi"."alerts"
                        WHERE user_id = :user_id AND read = FALSE
                    '''),
                    {"user_id": user_id}
                )
                row = result.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to get unread count for user {user_id}: {e}")
            return 0

    # Used by: alerts.py (POST mark single alert as read endpoint)
    async def mark_as_read(self, alert_id: int, user_id: int) -> bool:
        """Mark a single alert as read."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        UPDATE "Nappi"."alerts"
                        SET read = TRUE
                        WHERE id = :alert_id AND user_id = :user_id
                        RETURNING id
                    '''),
                    {"alert_id": alert_id, "user_id": user_id}
                )
                await session.commit()
                return result.fetchone() is not None
        except Exception as e:
            logger.error(f"Failed to mark alert {alert_id} as read: {e}")
            return False

    # Used by: alerts.py (POST mark all alerts as read endpoint)
    async def mark_all_as_read(self, user_id: int) -> int:
        """Mark all alerts as read for a user."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        UPDATE "Nappi"."alerts"
                        SET read = TRUE
                        WHERE user_id = :user_id AND read = FALSE
                    '''),
                    {"user_id": user_id}
                )
                await session.commit()
                return result.rowcount
        except Exception as e:
            logger.error(f"Failed to mark all alerts as read for user {user_id}: {e}")
            return 0

    # Used by: alerts.py (DELETE alerts endpoint)
    async def delete_alerts(self, alert_ids: List[int], user_id: int) -> int:
        """Delete alerts by IDs for a user."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        DELETE FROM "Nappi"."alerts"
                        WHERE id = ANY(:alert_ids) AND user_id = :user_id
                    '''),
                    {"alert_ids": alert_ids, "user_id": user_id}
                )
                await session.commit()
                return result.rowcount
        except Exception as e:
            logger.error(f"Failed to delete alerts for user {user_id}: {e}")
            return 0

    # Used by: tasks.py (sensor polling)
    async def check_thresholds(
        self,
        baby_id: int,
        temperature: Optional[float] = None,
        humidity: Optional[float] = None,
        noise_db: Optional[float] = None,
        user_id: Optional[int] = None
    ) -> List[Alert]:
        """Check sensor values against thresholds and create alerts if exceeded."""
        if user_id is None:
            user_id = await self.get_user_id_for_baby(baby_id)
            if user_id is None:
                logger.warning(f"No user found for baby {baby_id}, skipping threshold alerts")
                return []

        alerts = []
        noise = noise_db

        if temperature is not None:
            if temperature > TEMP_HIGH:
                if not self._is_alert_on_cooldown(baby_id, AlertType.TEMPERATURE):
                    alert = await self.create_alert(
                        baby_id=baby_id,
                        user_id=user_id,
                        alert_type=AlertType.TEMPERATURE,
                        title="Room temperature update",
                        message=f"We noticed the temperature is at {temperature:.1f}°C — you might want to cool the room a bit.",
                        severity=AlertSeverity.WARNING,
                        metadata={"value": temperature, "threshold": TEMP_HIGH, "direction": "high"}
                    )
                    if alert:
                        self._set_alert_cooldown(baby_id, AlertType.TEMPERATURE)
                        alerts.append(alert)
            elif temperature < TEMP_LOW:
                if not self._is_alert_on_cooldown(baby_id, AlertType.TEMPERATURE):
                    alert = await self.create_alert(
                        baby_id=baby_id,
                        user_id=user_id,
                        alert_type=AlertType.TEMPERATURE,
                        title="Room temperature update",
                        message=f"We noticed the temperature is at {temperature:.1f}°C — it might help to warm the room a little.",
                        severity=AlertSeverity.WARNING,
                        metadata={"value": temperature, "threshold": TEMP_LOW, "direction": "low"}
                    )
                    if alert:
                        self._set_alert_cooldown(baby_id, AlertType.TEMPERATURE)
                        alerts.append(alert)

        if humidity is not None:
            if humidity > HUMIDITY_HIGH:
                if not self._is_alert_on_cooldown(baby_id, AlertType.HUMIDITY):
                    alert = await self.create_alert(
                        baby_id=baby_id,
                        user_id=user_id,
                        alert_type=AlertType.HUMIDITY,
                        title="Room humidity update",
                        message=f"Humidity is at {humidity:.0f}% — a dehumidifier might help keep things comfortable.",
                        severity=AlertSeverity.WARNING,
                        metadata={"value": humidity, "threshold": HUMIDITY_HIGH, "direction": "high"}
                    )
                    if alert:
                        self._set_alert_cooldown(baby_id, AlertType.HUMIDITY)
                        alerts.append(alert)
            elif humidity < HUMIDITY_LOW:
                if not self._is_alert_on_cooldown(baby_id, AlertType.HUMIDITY):
                    alert = await self.create_alert(
                        baby_id=baby_id,
                        user_id=user_id,
                        alert_type=AlertType.HUMIDITY,
                        title="Room humidity update",
                        message=f"Humidity is at {humidity:.0f}% — a humidifier could help keep the air comfortable.",
                        severity=AlertSeverity.WARNING,
                        metadata={"value": humidity, "threshold": HUMIDITY_LOW, "direction": "low"}
                    )
                    if alert:
                        self._set_alert_cooldown(baby_id, AlertType.HUMIDITY)
                        alerts.append(alert)

        if noise is not None:
            if noise > NOISE_HIGH:
                if not self._is_alert_on_cooldown(baby_id, AlertType.NOISE):
                    alert = await self.create_alert(
                        baby_id=baby_id,
                        user_id=user_id,
                        alert_type=AlertType.NOISE,
                        title="Noise level update",
                        message=f"We picked up some noise in the room ({noise:.0f}dB) — it could be worth checking on.",
                        severity=AlertSeverity.WARNING,
                        metadata={"value": noise, "threshold": NOISE_HIGH}
                    )
                    if alert:
                        self._set_alert_cooldown(baby_id, AlertType.NOISE)
                        alerts.append(alert)

        return alerts

    # Used by: sensor_events.py (sleep-end endpoint)
    async def create_awakening_alert(
        self,
        baby_id: int,
        sleep_duration_minutes: float,
        awakened_at: datetime,
        last_sensor_readings: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None
    ) -> Optional[Alert]:
        """Create an alert when a baby wakes up."""
        if user_id is None:
            user_id = await self.get_user_id_for_baby(baby_id)
            if user_id is None:
                logger.warning(f"No user found for baby {baby_id}, skipping awakening alert")
                return None
        hours = int(sleep_duration_minutes // 60)
        minutes = int(sleep_duration_minutes % 60)
        if hours > 0:
            duration_str = f"{hours}h {minutes}m"
        else:
            duration_str = f"{minutes} minutes"

        time_str = awakened_at.strftime("%H:%M")

        metadata = {
            "sleep_duration_minutes": sleep_duration_minutes,
            "awakened_at": awakened_at.isoformat()
        }
        if last_sensor_readings:
            metadata["last_sensor_readings"] = {
                k: v.isoformat() if isinstance(v, datetime) else v
                for k, v in last_sensor_readings.items()
            }

        return await self.create_alert(
            baby_id=baby_id,
            user_id=user_id,
            alert_type=AlertType.AWAKENING,
            title="Baby woke up",
            message=f"Baby woke up at {time_str} after sleeping for {duration_str}.",
            severity=AlertSeverity.INFO,
            metadata=metadata
        )

    # Used by: self.create_alert()
    async def _send_push_notification(self, user_id: int, alert: Alert):
        """Send a web push notification for an alert."""
        try:
            # Import push service here to avoid circular imports
            from app.services.push_service import get_push_service
            push_service = get_push_service()
            await push_service.send_notification(
                user_id=user_id,
                title=alert.title,
                body=alert.message,
                data={"alert_id": alert.id, "type": alert.type}
            )
        except Exception as e:
            # Don't fail the alert creation if push fails
            logger.warning(f"Failed to send push notification for alert {alert.id}: {e}")


_alert_service: Optional[AlertService] = None


# Used by: sensor_events.py, tasks.py, alerts.py
def get_alert_service() -> AlertService:
    """Get the alert service singleton."""
    global _alert_service
    if _alert_service is None:
        _alert_service = AlertService()
    return _alert_service
