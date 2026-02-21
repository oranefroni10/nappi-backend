"""
Schedule Predictor Service - Predicts upcoming sleep windows based on patterns.

This service provides:
1. Prediction of next likely nap/sleep time based on historical patterns
2. Optimal bedtime suggestions based on baby's data
3. Wake window recommendations based on age
4. Current sleep status and time since last wake
"""

import logging
from datetime import datetime, timedelta, time, date
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from statistics import mean, median

from .babies_data import BabyDataManager
from .sleep_patterns import analyze_sleep_patterns

logger = logging.getLogger(__name__)

# Age-based wake window recommendations (in hours)
# See README.md "Sleep Guidelines Sources" section for full source citations
WAKE_WINDOWS = {
    # (min_months, max_months): (min_wake_hours, max_wake_hours)
    (0, 1): (0.5, 1.0),  # 30-60 min
    (2, 3): (1.0, 2.0),  # 1-2 hours
    (4, 5): (1.25, 2.5),  # 1.25-2.5 hours
    (6, 7): (2.0, 4.0),  # 2-4 hours
    (8, 9): (2.5, 4.5),  # 2.5-4.5 hours
    (10, 12): (3.0, 4.0),  # 3-4 hours
    (13, 18): (3.0, 5.5),  # 3-5.5 hours
    (19, 24): (4.0, 6.0),  # 4-6 hours
    (25, 36): (5.0, 6.0),  # 5-6 hours
}

# Typical bedtimes by age
# fallback data based on online research
TYPICAL_BEDTIMES = {
    (0, 3): (20, 0, 23, 0),  # 8:00 PM - 11:00 PM (newborns: no circadian rhythm yet)
    (4, 6): (19, 0, 20, 30),  # 7:00 PM - 8:30 PM (circadian rhythm maturing)
    (7, 12): (18, 30, 20, 0),  # 6:30 PM - 8:00 PM (earliest bedtimes of infancy)
    (13, 24): (19, 0, 20, 0),  # 7:00 PM - 8:00 PM
    (25, 36): (19, 0, 20, 30),  # 7:00 PM - 8:30 PM
}


# Used by: SchedulePredictor.predict_next_sleep() (wake window lookup)
def get_wake_window(age_months: int) -> Tuple[float, float]:
    """Get recommended wake window range for a specific age."""
    for (min_age, max_age), window in WAKE_WINDOWS.items():
        if min_age <= age_months <= max_age:
            return window
    return (5.0, 6.0)  # Default for older children


# Used by: SchedulePredictor.predict_next_sleep() (bedtime lookup)
def get_typical_bedtime(age_months: int) -> Tuple[time, time]:
    """Get typical bedtime range for a specific age."""
    for (min_age, max_age), times in TYPICAL_BEDTIMES.items():
        if min_age <= age_months <= max_age:
            return (time(times[0], times[1]), time(times[2], times[3]))
    return (time(19, 0), time(20, 30))


@dataclass
class SleepPrediction:
    """Prediction for next sleep window."""
    predicted_start: datetime
    confidence: str  # "high", "medium", "low"
    prediction_type: str  # "nap", "bedtime"
    based_on: str  # Description of what the prediction is based on
    time_until: timedelta
    wake_window_status: str  # "optimal", "approaching", "overdue"


@dataclass
class ScheduleRecommendation:
    """Complete schedule recommendation."""
    next_sleep: Optional[SleepPrediction]
    optimal_bedtime: time
    current_wake_duration: Optional[timedelta]
    wake_window_range: Tuple[float, float]
    suggestions: List[str]


# Used by: get_schedule_prediction() convenience function
class SchedulePredictor:
    """
    Predicts sleep schedules based on historical patterns and age-appropriate guidelines.
    """

    def __init__(self):
        self.baby_manager = BabyDataManager()

    # Used by: get_schedule_prediction() convenience function
    async def predict_next_sleep(
            self,
            baby_id: int,
            current_time: Optional[datetime] = None
    ) -> Optional[ScheduleRecommendation]:
        """
        Predict the next sleep window for a baby.
        
        Args:
            baby_id: The ID of the baby
            current_time: Current time (defaults to now)
            
        Returns:
            ScheduleRecommendation with prediction details
        """
        if current_time is None:
            current_time = datetime.now()

        logger.info(f"Predicting next sleep for baby {baby_id}")

        # Get baby info for age
        baby = await self.baby_manager.get_baby_by_id(baby_id)
        if not baby:
            logger.warning(f"Baby {baby_id} not found")
            return None

        # Calculate age in months
        today = current_time.date()
        age_days = (today - baby.birthdate).days
        age_months = age_days // 30

        # Get wake window for this age
        wake_window = get_wake_window(age_months)
        typical_bedtime = get_typical_bedtime(age_months)

        # Get most recent awakening to calculate current wake duration
        latest_event = await self.baby_manager.get_latest_awakening_event(baby_id)

        current_wake_duration = None
        if latest_event and latest_event.get("awakened_at"):
            last_wake = latest_event["awakened_at"]
            if isinstance(last_wake, datetime):
                current_wake_duration = current_time - last_wake

        # Get sleep patterns from recent weeks
        now = datetime.now()
        patterns = await self._get_recent_patterns(baby_id, now.month, now.year)

        # Generate prediction
        prediction = self._generate_prediction(
            patterns=patterns,
            current_time=current_time,
            wake_duration=current_wake_duration,
            wake_window=wake_window,
            age_months=age_months
        )

        # Generate suggestions
        suggestions = self._generate_suggestions(
            prediction=prediction,
            wake_duration=current_wake_duration,
            wake_window=wake_window,
            age_months=age_months,
            baby_name=baby.first_name
        )

        return ScheduleRecommendation(
            next_sleep=prediction,
            optimal_bedtime=self._calculate_optimal_bedtime(patterns, typical_bedtime),
            current_wake_duration=current_wake_duration,
            wake_window_range=wake_window,
            suggestions=suggestions
        )

    # Used by: predict_next_sleep() (fetches and analyzes recent sleep patterns)
    async def _get_recent_patterns(
            self,
            baby_id: int,
            month: int,
            year: int
    ) -> List[Dict[str, Any]]:
        """Get analyzed sleep patterns from recent data."""
        # Get this month's sessions
        sessions = await self.baby_manager.get_sleep_sessions_for_month(
            baby_id=baby_id,
            year=year,
            month=month
        )

        if not sessions:
            # Try previous month
            prev_month = month - 1 if month > 1 else 12
            prev_year = year if month > 1 else year - 1
            sessions = await self.baby_manager.get_sleep_sessions_for_month(
                baby_id=baby_id,
                year=prev_year,
                month=prev_month
            )

        if not sessions:
            return []

        # Analyze patterns
        patterns = analyze_sleep_patterns(sessions)
        return patterns

    # Used by: predict_next_sleep() (generates prediction from patterns and wake window)
    def _generate_prediction(
            self,
            patterns: List[Dict[str, Any]],
            current_time: datetime,
            wake_duration: Optional[timedelta],
            wake_window: Tuple[float, float],
            age_months: int
    ) -> Optional[SleepPrediction]:
        """Generate sleep prediction based on available data."""

        current_hour = current_time.hour + current_time.minute / 60.0
        min_wake, max_wake = wake_window

        # Method 1: Based on wake window
        if wake_duration:
            wake_hours = wake_duration.total_seconds() / 3600.0

            # Determine wake window status
            if wake_hours < min_wake * 0.8:
                wake_status = "recently_woke"
            elif wake_hours < min_wake:
                wake_status = "not_yet"
            elif wake_hours <= max_wake:
                wake_status = "optimal"
            elif wake_hours <= max_wake * 1.2:
                wake_status = "approaching"
            else:
                wake_status = "overdue"

            # Predict based on wake window
            if wake_status in ["optimal", "approaching", "overdue"]:
                # Baby should sleep soon
                if wake_status == "overdue":
                    predicted_start = current_time + timedelta(minutes=15)
                    confidence = "high"
                    based_on = "Wake window exceeded - sleep signs likely"
                elif wake_status == "approaching":
                    predicted_start = current_time + timedelta(minutes=30)
                    confidence = "high"
                    based_on = f"Approaching {max_wake:.1f}h wake window limit"
                else:
                    time_to_max = timedelta(hours=(max_wake - wake_hours))
                    predicted_start = current_time + time_to_max
                    confidence = "medium"
                    based_on = "Within optimal wake window"

                # Determine if nap or bedtime
                predicted_hour = predicted_start.hour
                prediction_type = "bedtime" if 17 <= predicted_hour <= 22 else "nap"

                return SleepPrediction(
                    predicted_start=predicted_start,
                    confidence=confidence,
                    prediction_type=prediction_type,
                    based_on=based_on,
                    time_until=predicted_start - current_time,
                    wake_window_status=wake_status
                )

        # Method 2: Based on historical patterns
        if patterns:
            # Find the next pattern that typically occurs after current time
            for pattern in patterns:
                avg_start = pattern.get("avg_start", "")
                if avg_start:
                    try:
                        pattern_hour = self._time_str_to_decimal(avg_start)

                        # Pattern is after current time
                        if pattern_hour > current_hour:
                            hours_until = pattern_hour - current_hour
                            predicted_start = current_time + timedelta(hours=hours_until)

                            return SleepPrediction(
                                predicted_start=predicted_start,
                                confidence="medium",
                                prediction_type="nap" if pattern.get("label",
                                                                     "").lower() != "night sleep" else "bedtime",
                                based_on=f"Typical {pattern.get('label', 'sleep')} pattern",
                                time_until=timedelta(hours=hours_until),
                                wake_window_status="unknown"
                            )
                    except:
                        continue

        # Method 3: Fallback based on time of day and age
        predicted_start = self._fallback_prediction(current_time, age_months)
        hours_until = (predicted_start - current_time).total_seconds() / 3600.0

        return SleepPrediction(
            predicted_start=predicted_start,
            confidence="low",
            prediction_type="bedtime" if 17 <= predicted_start.hour <= 22 else "nap",
            based_on="Age-based estimate (limited data available)",
            time_until=predicted_start - current_time,
            wake_window_status="unknown"
        )

    # Used by: _generate_prediction() (fallback when no patterns or wake data)
    def _fallback_prediction(self, current_time: datetime, age_months: int) -> datetime:
        """Generate fallback prediction based on time of day and age."""
        hour = current_time.hour

        # Morning (6-11): Suggest late morning nap
        if 6 <= hour < 11:
            return current_time.replace(hour=10, minute=30, second=0, microsecond=0)

        # Late morning (11-14): Suggest afternoon nap
        elif 11 <= hour < 14:
            return current_time.replace(hour=13, minute=30, second=0, microsecond=0)

        # Afternoon (14-17): Suggest late afternoon nap or early bedtime
        elif 14 <= hour < 17:
            if age_months < 12:
                return current_time.replace(hour=16, minute=0, second=0, microsecond=0)
            else:
                return current_time.replace(hour=18, minute=30, second=0, microsecond=0)

        # Evening (17+): Suggest bedtime
        else:
            bedtime_hour = 19 if age_months < 12 else 20
            target = current_time.replace(hour=bedtime_hour, minute=0, second=0, microsecond=0)
            if target <= current_time:
                target = target + timedelta(days=1)
            return target

    # Used by: _generate_prediction() (parses pattern avg_start times)
    def _time_str_to_decimal(self, time_str: str) -> float:
        """Convert HH:MM to decimal hours."""
        parts = time_str.split(":")
        return int(parts[0]) + int(parts[1]) / 60.0

    # Used by: predict_next_sleep() (determines optimal bedtime for recommendation)
    def _calculate_optimal_bedtime(
            self,
            patterns: List[Dict[str, Any]],
            typical_bedtime: Tuple[time, time]
    ) -> time:
        """Calculate optimal bedtime based on patterns."""

        # Look for night sleep pattern
        for pattern in patterns:
            label = pattern.get("label", "").lower()
            if "night" in label:
                avg_start = pattern.get("avg_start", "")
                if avg_start:
                    try:
                        parts = avg_start.split(":")
                        return time(int(parts[0]), int(parts[1]))
                    except:
                        pass

        # Use typical bedtime middle point
        min_bed, max_bed = typical_bedtime
        avg_hour = (min_bed.hour + max_bed.hour) / 2
        avg_minute = (min_bed.minute + max_bed.minute) / 2
        return time(int(avg_hour), int(avg_minute))

    # Used by: predict_next_sleep() (generates actionable text suggestions)
    def _generate_suggestions(
            self,
            prediction: Optional[SleepPrediction],
            wake_duration: Optional[timedelta],
            wake_window: Tuple[float, float],
            age_months: int,
            baby_name: str
    ) -> List[str]:
        """Generate actionable suggestions based on current state."""
        suggestions = []
        min_wake, max_wake = wake_window

        if wake_duration:
            wake_hours = wake_duration.total_seconds() / 3600.0

            if wake_hours > max_wake * 1.2:
                suggestions.append(f"{baby_name} may be overtired - watch for fussy cues and consider an early nap")
            elif wake_hours > max_wake:
                suggestions.append(f"Approaching overtired territory - start wind-down routine now")
            elif wake_hours >= min_wake:
                suggestions.append(f"Within optimal wake window ({min_wake:.1f}-{max_wake:.1f}h) - good time for sleep")
            else:
                remaining = min_wake - wake_hours
                suggestions.append(f"About {remaining:.1f}h until optimal nap window")

        if prediction:
            if prediction.confidence == "high":
                suggestions.append(
                    f"Start sleep routine 15-20 minutes before {prediction.predicted_start.strftime('%I:%M %p')}")
            elif prediction.prediction_type == "bedtime":
                suggestions.append(
                    f"Begin calming bedtime routine around {prediction.predicted_start.strftime('%I:%M %p')}")

        # Age-specific suggestions
        if age_months <= 3:
            suggestions.append("At this age, follow baby's cues - patterns will emerge over time")
        elif age_months <= 6:
            suggestions.append("Establish consistent pre-sleep routines for better sleep associations")

        return suggestions[:3]  # Limit to 3 suggestions


# Used by: stats.py (GET /stats/schedule, GET /stats/comprehensive)
async def get_schedule_prediction(baby_id: int) -> Dict[str, Any]:
    """
    Get schedule prediction for a baby.
    
    Args:
        baby_id: The ID of the baby
        
    Returns:
        Dictionary with prediction details
    """
    predictor = SchedulePredictor()
    recommendation = await predictor.predict_next_sleep(baby_id)

    if not recommendation:
        return {"error": "Could not generate prediction"}

    result = {
        "baby_id": baby_id,
        "generated_at": datetime.now().isoformat(),
        "wake_window_range_hours": {
            "min": recommendation.wake_window_range[0],
            "max": recommendation.wake_window_range[1]
        },
        "optimal_bedtime": recommendation.optimal_bedtime.strftime("%H:%M"),
        "suggestions": recommendation.suggestions
    }

    if recommendation.current_wake_duration:
        result["current_wake_duration_minutes"] = int(
            recommendation.current_wake_duration.total_seconds() / 60
        )

    if recommendation.next_sleep:
        pred = recommendation.next_sleep
        result["next_sleep"] = {
            "predicted_time": pred.predicted_start.isoformat(),
            "predicted_time_formatted": pred.predicted_start.strftime("%I:%M %p"),
            "confidence": pred.confidence,
            "type": pred.prediction_type,
            "based_on": pred.based_on,
            "minutes_until": int(pred.time_until.total_seconds() / 60),
            "wake_window_status": pred.wake_window_status
        }

    return result
