"""Groups consecutive awakening events into logical sleep blocks."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from app.core.constants import SLEEP_BLOCK_GAP_THRESHOLD_MINUTES

logger = logging.getLogger(__name__)

DEFAULT_GAP_THRESHOLD_MINUTES = SLEEP_BLOCK_GAP_THRESHOLD_MINUTES


# Used by: group_into_sleep_blocks() return; stats.py, chat_service.py, correlation_analyzer.py, trend_analyzer.py, daily_summary.py
@dataclass
class SleepBlock:
    block_start: datetime
    block_end: datetime
    total_sleep_minutes: float
    total_block_minutes: float
    interruption_count: int
    event_count: int
    events: List[Dict[str, Any]] = field(default_factory=list)


# Used by: stats.py (GET /stats/daily-sleep), chat_service.py, correlation_analyzer.py, trend_analyzer.py, daily_summary.py
def group_into_sleep_blocks(
    events: List[Dict[str, Any]],
    gap_threshold_minutes: float = DEFAULT_GAP_THRESHOLD_MINUTES,
    source: str = "auto"
) -> List[SleepBlock]:
    """Events within gap_threshold_minutes are grouped together."""
    if not events:
        return []

    normalized = []
    for event in events:
        n = _normalize_event(event, source)
        if n:
            normalized.append(n)

    if not normalized:
        return []

    normalized.sort(key=lambda e: e["sleep_started_at"])

    blocks = []
    current_block_events = [normalized[0]]

    for i in range(1, len(normalized)):
        prev = current_block_events[-1]
        curr = normalized[i]

        gap = (curr["sleep_started_at"] - prev["awakened_at"]).total_seconds() / 60.0

        if gap <= gap_threshold_minutes:
            current_block_events.append(curr)
        else:
            blocks.append(_build_block(current_block_events))
            current_block_events = [curr]

    blocks.append(_build_block(current_block_events))

    return blocks


# Used by: _normalize_event() when source="auto"
def _detect_source(event: Dict[str, Any]) -> str:
    if "event_metadata" in event:
        return "events_for_period"
    if "ai_insight" in event:
        return "awakenings_with_insights"
    if "session_date" in event:
        return "sessions_for_range"
    return "unknown"


# Used by: _normalize_event()
def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    return None


# Used by: group_into_sleep_blocks()
def _normalize_event(event: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    """Returns dict with sleep_started_at, awakened_at, duration_minutes, original; or None if fails."""
    if source == "auto":
        source = _detect_source(event)

    try:
        if source == "awakenings_with_insights":
            awakened_at = _parse_timestamp(event.get("awakened_at"))
            duration = event.get("sleep_duration_minutes") or 0.0
            if not awakened_at:
                return None
            sleep_started_at = awakened_at - timedelta(minutes=duration)
            return {
                "sleep_started_at": sleep_started_at,
                "awakened_at": awakened_at,
                "duration_minutes": duration,
                "original": event,
            }

        elif source == "events_for_period":
            metadata = event.get("event_metadata", {})
            if isinstance(metadata, str):
                import json
                metadata = json.loads(metadata)
            sleep_started_at = _parse_timestamp(metadata.get("sleep_started_at"))
            awakened_at = _parse_timestamp(metadata.get("awakened_at"))
            duration = metadata.get("sleep_duration_minutes") or 0.0
            if not sleep_started_at or not awakened_at:
                return None
            return {
                "sleep_started_at": sleep_started_at,
                "awakened_at": awakened_at,
                "duration_minutes": duration,
                "original": event,
            }

        elif source == "sessions_for_range":
            sleep_started_at = _parse_timestamp(event.get("sleep_started_at"))
            awakened_at = _parse_timestamp(event.get("awakened_at"))
            duration = event.get("duration_minutes") or 0.0
            if not sleep_started_at or not awakened_at:
                return None
            return {
                "sleep_started_at": sleep_started_at,
                "awakened_at": awakened_at,
                "duration_minutes": duration,
                "original": event,
            }

        else:
            logger.warning(f"Unknown sleep block source: {source}")
            return None

    except Exception as e:
        logger.warning(f"Failed to normalize event ({source}): {e}")
        return None


# Used by: group_into_sleep_blocks()
def _build_block(normalized_events: List[Dict[str, Any]]) -> SleepBlock:
    block_start = normalized_events[0]["sleep_started_at"]
    block_end = normalized_events[-1]["awakened_at"]
    total_sleep = sum(e["duration_minutes"] for e in normalized_events)
    total_block = (block_end - block_start).total_seconds() / 60.0

    return SleepBlock(
        block_start=block_start,
        block_end=block_end,
        total_sleep_minutes=total_sleep,
        total_block_minutes=total_block,
        interruption_count=len(normalized_events) - 1,
        event_count=len(normalized_events),
        events=[e["original"] for e in normalized_events],
    )
