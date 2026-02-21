"""
Sleep Patterns Service - Analyzes sleep sessions to find typical patterns.

This service clusters sleep sessions by start time proximity and calculates
averaged time ranges for each cluster (e.g., "Morning nap: 8:45 - 10:50").
"""

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

# Gap threshold for clustering (hours) — from centralized constants
DEFAULT_GAP_HOURS = SLEEP_PATTERN_GAP_HOURS


@dataclass
class SleepSession:
    """A single sleep session extracted from awakening_events."""
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    
    @property
    def start_hour_decimal(self) -> float:
        """Start time as decimal hours (e.g., 8:30 = 8.5)."""
        return self.start_time.hour + self.start_time.minute / 60.0
    
    @property
    def end_hour_decimal(self) -> float:
        """End time as decimal hours, handling overnight (e.g., 6 AM = 30.0 if started at night)."""
        end_decimal = self.end_time.hour + self.end_time.minute / 60.0
        # If end is earlier than start (overnight), add 24
        if end_decimal < self.start_hour_decimal:
            end_decimal += 24.0
        return end_decimal


@dataclass
class SleepCluster:
    """A cluster of similar sleep sessions."""
    sessions: List[SleepSession]
    
    @property
    def avg_start_hour(self) -> float:
        """Average start hour as decimal."""
        if not self.sessions:
            return 0.0
        return sum(s.start_hour_decimal for s in self.sessions) / len(self.sessions)
    
    @property
    def avg_end_hour(self) -> float:
        """Average end hour as decimal."""
        if not self.sessions:
            return 0.0
        return sum(s.end_hour_decimal for s in self.sessions) / len(self.sessions)
    
    @property
    def avg_duration_hours(self) -> float:
        """Average duration in hours."""
        if not self.sessions:
            return 0.0
        return sum(s.duration_minutes for s in self.sessions) / len(self.sessions) / 60.0
    
    @property
    def earliest_start_hour(self) -> float:
        """Earliest start hour in the cluster."""
        if not self.sessions:
            return 0.0
        return min(s.start_hour_decimal for s in self.sessions)
    
    @property
    def latest_end_hour(self) -> float:
        """Latest end hour in the cluster."""
        if not self.sessions:
            return 0.0
        return max(s.end_hour_decimal for s in self.sessions)


# Used by: analyze_sleep_patterns() (parses raw DB rows into SleepSession objects)
def parse_sleep_sessions(raw_sessions: List[Dict[str, Any]]) -> List[SleepSession]:
    """
    Parse raw database rows into SleepSession objects.
    
    Args:
        raw_sessions: List of dicts with sleep_started_at, awakened_at, duration_minutes
        
    Returns:
        List of parsed SleepSession objects
    """
    sessions = []
    
    for row in raw_sessions:
        try:
            start_str = row.get("sleep_started_at")
            end_str = row.get("awakened_at")
            duration = row.get("duration_minutes")
            
            if not start_str or not end_str:
                continue
            
            # Parse ISO timestamps
            start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            
            # Remove timezone info for simpler hour calculations
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


# Used by: analyze_sleep_patterns() (groups sessions into time-of-day clusters)
def cluster_by_start_time(
    sessions: List[SleepSession],
    gap_hours: float = DEFAULT_GAP_HOURS
) -> List[SleepCluster]:
    """
    Cluster sleep sessions by start time proximity.
    
    Algorithm:
    1. Sort sessions by start hour (time of day, ignoring date)
    2. Create new cluster when gap between consecutive start times > gap_hours
    
    Args:
        sessions: List of SleepSession objects
        gap_hours: Minimum gap (in hours) to start a new cluster
        
    Returns:
        List of SleepCluster objects
    """
    if not sessions:
        return []
    
    # Sort by start hour (time of day)
    sorted_sessions = sorted(sessions, key=lambda s: s.start_hour_decimal)
    
    clusters: List[SleepCluster] = []
    current_cluster_sessions: List[SleepSession] = [sorted_sessions[0]]
    
    for i in range(1, len(sorted_sessions)):
        prev_start = sorted_sessions[i - 1].start_hour_decimal
        curr_start = sorted_sessions[i].start_hour_decimal
        gap = curr_start - prev_start
        
        if gap > gap_hours:
            # Start new cluster
            clusters.append(SleepCluster(sessions=current_cluster_sessions))
            current_cluster_sessions = [sorted_sessions[i]]
        else:
            # Add to current cluster
            current_cluster_sessions.append(sorted_sessions[i])
    
    # Don't forget the last cluster
    if current_cluster_sessions:
        clusters.append(SleepCluster(sessions=current_cluster_sessions))
    
    return clusters


# Used by: analyze_sleep_patterns() (formats cluster hours as HH:MM strings)
def decimal_to_time_str(decimal_hours: float) -> str:
    """
    Convert decimal hours to HH:MM string.
    
    Args:
        decimal_hours: Hours as decimal (e.g., 8.5 = 8:30)
        
    Returns:
        Time string in HH:MM format
    """
    # Handle values > 24 (overnight)
    decimal_hours = decimal_hours % 24.0
    
    hours = int(decimal_hours)
    minutes = int((decimal_hours - hours) * 60)
    
    return f"{hours:02d}:{minutes:02d}"


# Used by: analyze_sleep_patterns() (labels clusters as Morning nap/Afternoon nap/Night sleep)
def assign_label(avg_start_hour: float) -> str:
    """
    Assign a human-readable label based on average start hour.
    
    Args:
        avg_start_hour: Average start hour as decimal
        
    Returns:
        Label string ("Morning nap", "Afternoon nap", or "Night sleep")
    """
    # Normalize to 0-24 range
    hour = avg_start_hour % 24.0
    
    if float(PATTERN_MORNING_START) <= hour < float(PATTERN_MORNING_END):
        return "Morning nap"
    elif float(PATTERN_AFTERNOON_START) <= hour < float(PATTERN_AFTERNOON_END):
        return "Afternoon nap"
    else:
        return "Night sleep"


# Used by: stats.py (GET /stats/patterns), chat_service.py (chat context), schedule_predictor.py (_get_recent_patterns)
def analyze_sleep_patterns(
    raw_sessions: List[Dict[str, Any]],
    gap_hours: float = DEFAULT_GAP_HOURS
) -> List[Dict[str, Any]]:
    """
    Main function to analyze sleep sessions and return patterns.
    
    Args:
        raw_sessions: Raw database rows with sleep session data
        gap_hours: Gap threshold for clustering
        
    Returns:
        List of pattern dictionaries ready for API response
    """
    # Parse sessions
    sessions = parse_sleep_sessions(raw_sessions)
    
    if not sessions:
        return []
    
    # Cluster by start time
    clusters = cluster_by_start_time(sessions, gap_hours)
    
    # Build response patterns
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
    
    # Sort by avg_start for consistent ordering
    patterns.sort(key=lambda p: _time_str_to_sort_key(p["avg_start"]))
    
    # Re-assign cluster IDs after sorting
    for idx, pattern in enumerate(patterns):
        pattern["cluster_id"] = idx + 1
    
    return patterns


# Used by: analyze_sleep_patterns() (sorts patterns by time of day)
def _time_str_to_sort_key(time_str: str) -> float:
    """Convert HH:MM to decimal for sorting, treating night times (20:00+) as later."""
    parts = time_str.split(":")
    hour = int(parts[0])
    minute = int(parts[1])
    decimal = hour + minute / 60.0
    
    # Treat times after 8 PM as "later" for sorting (so night comes last)
    if hour < 5:
        decimal += 24.0
    
    return decimal

