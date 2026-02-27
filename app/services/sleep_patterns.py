"""Clusters sleep sessions by start time and computes averaged time ranges."""

import logging
from datetime import datetime, time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from app.core.constants import (
    SLEEP_PATTERN_GAP_HOURS,
    PATTERN_MORNING_START, PATTERN_MORNING_END,
    PATTERN_AFTERNOON_START, PATTERN_AFTERNOON_END,
)

logger = logging.getLogger(__name__)

DEFAULT_GAP_HOURS = SLEEP_PATTERN_GAP_HOURS


@dataclass
class SleepSession:
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    
    @property
    def start_hour_decimal(self) -> float:
        return self.start_time.hour + self.start_time.minute / 60.0
    
    @property
    def end_hour_decimal(self) -> float:
        """End time as decimal hours, handling overnight."""
        end_decimal = self.end_time.hour + self.end_time.minute / 60.0
        # If end is earlier than start (overnight), add 24
        if end_decimal < self.start_hour_decimal:
            end_decimal += 24.0
        return end_decimal


@dataclass
class SleepCluster:
    sessions: List[SleepSession]
    
    @property
    def avg_start_hour(self) -> float:
        if not self.sessions:
            return 0.0
        return sum(s.start_hour_decimal for s in self.sessions) / len(self.sessions)
    
    @property
    def avg_end_hour(self) -> float:
        if not self.sessions:
            return 0.0
        return sum(s.end_hour_decimal for s in self.sessions) / len(self.sessions)
    
    @property
    def avg_duration_hours(self) -> float:
        if not self.sessions:
            return 0.0
        return sum(s.duration_minutes for s in self.sessions) / len(self.sessions) / 60.0
    
    @property
    def earliest_start_hour(self) -> float:
        if not self.sessions:
            return 0.0
        return min(s.start_hour_decimal for s in self.sessions)
    
    @property
    def latest_end_hour(self) -> float:
        if not self.sessions:
            return 0.0
        return max(s.end_hour_decimal for s in self.sessions)


# Used by: analyze_sleep_patterns() — parses raw DB rows into SleepSession objects
def parse_sleep_sessions(raw_sessions: List[Dict[str, Any]]) -> List[SleepSession]:
    sessions = []
    
    for row in raw_sessions:
        try:
            start_str = row.get("sleep_started_at")
            end_str = row.get("awakened_at")
            duration = row.get("duration_minutes")
            
            if not start_str or not end_str:
                continue
            
            start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            start_time = start_time.replace(tzinfo=None)
            end_time = end_time.replace(tzinfo=None)
            
            sessions.append(SleepSession(
                start_time=start_time,
                end_time=end_time,
                duration_minutes=duration or (end_time - start_time).total_seconds() / 60.0
            ))
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse sleep session: {e}")
            continue
    
    return sessions


# Used by: analyze_sleep_patterns() — groups sessions into time-of-day clusters
def cluster_by_start_time(
    sessions: List[SleepSession],
    gap_hours: float = DEFAULT_GAP_HOURS
) -> List[SleepCluster]:
    if not sessions:
        return []
    
    sorted_sessions = sorted(sessions, key=lambda s: s.start_hour_decimal)
    
    clusters: List[SleepCluster] = []
    current_cluster_sessions: List[SleepSession] = [sorted_sessions[0]]
    
    for i in range(1, len(sorted_sessions)):
        prev_start = sorted_sessions[i - 1].start_hour_decimal
        curr_start = sorted_sessions[i].start_hour_decimal
        gap = curr_start - prev_start
        
        if gap > gap_hours:
            clusters.append(SleepCluster(sessions=current_cluster_sessions))
            current_cluster_sessions = [sorted_sessions[i]]
        else:
            current_cluster_sessions.append(sorted_sessions[i])
    
    if current_cluster_sessions:
        clusters.append(SleepCluster(sessions=current_cluster_sessions))
    
    return clusters


# Used by: analyze_sleep_patterns() — formats cluster hours as HH:MM strings
def decimal_to_time_str(decimal_hours: float) -> str:
    # Handle values > 24 (overnight)
    decimal_hours = decimal_hours % 24.0
    
    hours = int(decimal_hours)
    minutes = int((decimal_hours - hours) * 60)
    
    return f"{hours:02d}:{minutes:02d}"


# Used by: analyze_sleep_patterns() — labels clusters as Morning nap/Afternoon nap/Night sleep
def assign_label(avg_start_hour: float) -> str:
    hour = avg_start_hour % 24.0
    
    if float(PATTERN_MORNING_START) <= hour < float(PATTERN_MORNING_END):
        return "Morning nap"
    elif float(PATTERN_AFTERNOON_START) <= hour < float(PATTERN_AFTERNOON_END):
        return "Afternoon nap"
    else:
        return "Night sleep"


# Used by: stats.py (GET /stats/sleep-patterns), chat_service.py, schedule_predictor.py
def analyze_sleep_patterns(
    raw_sessions: List[Dict[str, Any]],
    gap_hours: float = DEFAULT_GAP_HOURS
) -> List[Dict[str, Any]]:
    sessions = parse_sleep_sessions(raw_sessions)
    
    if not sessions:
        return []
    
    clusters = cluster_by_start_time(sessions, gap_hours)
    
    patterns = []
    
    for idx, cluster in enumerate(clusters):
        if not cluster.sessions:
            continue
        
        pattern = {
            "cluster_id": idx + 1,
            "label": assign_label(cluster.avg_start_hour),
            "avg_start": decimal_to_time_str(cluster.avg_start_hour),
            "avg_end": decimal_to_time_str(cluster.avg_end_hour),
            "avg_duration_hours": round(cluster.avg_duration_hours, 2),
            "session_count": len(cluster.sessions),
            "earliest_start": decimal_to_time_str(cluster.earliest_start_hour),
            "latest_end": decimal_to_time_str(cluster.latest_end_hour),
        }
        patterns.append(pattern)
    
    patterns.sort(key=lambda p: _time_str_to_sort_key(p["avg_start"]))
    
    for idx, pattern in enumerate(patterns):
        pattern["cluster_id"] = idx + 1
    
    return patterns


# Used by: analyze_sleep_patterns() — sorts patterns by time of day
def _time_str_to_sort_key(time_str: str) -> float:
    """Convert HH:MM to decimal for sorting."""
    parts = time_str.split(":")
    hour = int(parts[0])
    minute = int(parts[1])
    decimal = hour + minute / 60.0
    
    # Treat times before 5 AM as "later" for sorting (so night comes last)
    if hour < 5:
        decimal += 24.0
    
    return decimal
