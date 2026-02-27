"""Predicts sleep windows from patterns."""

import logging
from datetime import datetime, timedelta, time, date
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from statistics import mean, median

from .babies_data import BabyDataManager
from .sleep_patterns import analyze_sleep_patterns
from ..core.constants import (
    WAKE_WINDOWS, TYPICAL_BEDTIMES, DAYS_PER_MONTH,
    WAKE_WINDOW_RECENTLY_WOKE_FACTOR, WAKE_WINDOW_APPROACHING_FACTOR,
    PREDICTION_FALLBACK_APPROACHING_MINUTES, PREDICTION_FALLBACK_OVERDUE_MINUTES,
    BEDTIME_PREDICTION_AGE_THRESHOLD_MONTHS, FALLBACK_NAP_TIMES,
)

logger = logging.getLogger(__name__)


# Used by: SchedulePredictor.predict_next_sleep
def get_wake_window(age_months: int) -> Tuple[float, float]:
    """Get recommended wake window range for a specific age."""
    for (min_age, max_age), window in WAKE_WINDOWS.items():
        if min_age <= age_months <= max_age:
            return window
    return (5.0, 6.0)  # Default for older children


# Used by: SchedulePredictor.predict_next_sleep
def get_typical_bedtime(age_months: int) -> Tuple[time, time]:
    """Get typical bedtime range for a specific age."""
    for (min_age, max_age), times in TYPICAL_BEDTIMES.items():
        if min_age <= age_months <= max_age:
            return (time(times[0], times[1]), time(times[2], times[3]))
    return (time(19, 0), time(20, 30))


@dataclass
class SleepPrediction:
    predicted_start: datetime
    confidence: str  # "high", "medium", "low"
    prediction_type: str  # "nap", "bedtime"
    based_on: str
    time_until: timedelta
    wake_window_status: str  # "optimal", "approaching", "overdue"


@dataclass
class ScheduleRecommendation:
    next_sleep: Optional[SleepPrediction]
    optimal_bedtime: time
    current_wake_duration: Optional[timedelta]
    wake_window_range: Tuple[float, float]
    suggestions: List[str]


# Used by: get_schedule_prediction
class SchedulePredictor:
    def __init__(self):
        self.baby_manager = BabyDataManager()

    # Used by: get_schedule_prediction
    async def predict_next_sleep(
            self,
            baby_id: int,
            current_time: Optional[datetime] = None
    ) -> Optional[ScheduleRecommendation]:
        """Predict next sleep window for baby."""
        if current_time is None:
            current_time = datetime.now()

        logger.info(f"Predicting next sleep for baby {baby_id}")

        baby = await self.baby_manager.get_baby_by_id(baby_id)
        if not baby:
            logger.warning(f"Baby {baby_id} not found")
            return None

        today = current_time.date()
        age_days = (today - baby.birthdate).days
        age_months = age_days // DAYS_PER_MONTH

        wake_window = get_wake_window(age_months)
        typical_bedtime = get_typical_bedtime(age_months)

        latest_event = await self.baby_manager.get_latest_awakening_event(baby_id)

        current_wake_duration = None
        if latest_event and latest_event.get("awakened_at"):
            last_wake = latest_event["awakened_at"]
            if isinstance(last_wake, datetime):
                current_wake_duration = current_time - last_wake

        now = datetime.now()
        patterns = await self._get_recent_patterns(baby_id, now.month, now.year)

        prediction = self._generate_prediction(
            patterns=patterns,
            current_time=current_time,
            wake_duration=current_wake_duration,
            wake_window=wake_window,
            age_months=age_months
        )

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

    # Used by: predict_next_sleep
    async def _get_recent_patterns(
            self,
            baby_id: int,
            month: int,
            year: int
    ) -> List[Dict[str, Any]]:
        """Get analyzed sleep patterns from recent data."""
        sessions = await self.baby_manager.get_sleep_sessions_for_month(
            baby_id=baby_id,
            year=year,
            month=month
        )

        if not sessions:
            prev_month = month - 1 if month > 1 else 12
            prev_year = year if month > 1 else year - 1
            sessions = await self.baby_manager.get_sleep_sessions_for_month(
                baby_id=baby_id,
                year=prev_year,
                month=prev_month
            )

        if not sessions:
            return []

        patterns = analyze_sleep_patterns(sessions)
        return patterns

    # Used by: predict_next_sleep
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

        if wake_duration:
            wake_hours = wake_duration.total_seconds() / 3600.0

            if wake_hours < min_wake * WAKE_WINDOW_RECENTLY_WOKE_FACTOR:
                wake_status = "recently_woke"
            elif wake_hours < min_wake:
                wake_status = "not_yet"
            elif wake_hours <= max_wake:
                wake_status = "optimal"
            elif wake_hours <= max_wake * WAKE_WINDOW_APPROACHING_FACTOR:
                wake_status = "approaching"
            else:
                wake_status = "overdue"

            if wake_status in ["optimal", "approaching", "overdue"]:
                if wake_status == "overdue":
                    predicted_start = current_time + timedelta(minutes=PREDICTION_FALLBACK_APPROACHING_MINUTES)
                    confidence = "high"
                    based_on = "Wake window exceeded - sleep signs likely"
                elif wake_status == "approaching":
                    predicted_start = current_time + timedelta(minutes=PREDICTION_FALLBACK_OVERDUE_MINUTES)
                    confidence = "high"
                    based_on = f"Approaching {max_wake:.1f}h wake window limit"
                else:
                    time_to_max = timedelta(hours=(max_wake - wake_hours))
                    predicted_start = current_time + time_to_max
                    confidence = "medium"
                    based_on = "Within optimal wake window"

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

        if patterns:
            for pattern in patterns:
                avg_start = pattern.get("avg_start", "")
                if avg_start:
                    try:
                        pattern_hour = self._time_str_to_decimal(avg_start)

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

    # Used by: _generate_prediction
    def _fallback_prediction(self, current_time: datetime, age_months: int) -> datetime:
        """Fallback prediction from time of day and age."""
        hour = current_time.hour

        for before_hour, predict_hour, predict_minute in FALLBACK_NAP_TIMES:
            if hour < before_hour:
                return current_time.replace(hour=predict_hour, minute=predict_minute, second=0, microsecond=0)

        if hour < 17:
            if age_months < BEDTIME_PREDICTION_AGE_THRESHOLD_MONTHS:
                return current_time.replace(hour=16, minute=0, second=0, microsecond=0)
            else:
                return current_time.replace(hour=18, minute=30, second=0, microsecond=0)
        else:
            bedtime_hour = 19 if age_months < BEDTIME_PREDICTION_AGE_THRESHOLD_MONTHS else 20
            target = current_time.replace(hour=bedtime_hour, minute=0, second=0, microsecond=0)
            if target <= current_time:
                target = target + timedelta(days=1)
            return target

    # Used by: _generate_prediction
    def _time_str_to_decimal(self, time_str: str) -> float:
        """Convert HH:MM to decimal hours."""
        parts = time_str.split(":")
        return int(parts[0]) + int(parts[1]) / 60.0

    # Used by: predict_next_sleep
    def _calculate_optimal_bedtime(
            self,
            patterns: List[Dict[str, Any]],
            typical_bedtime: Tuple[time, time]
    ) -> time:
        """Optimal bedtime from patterns."""
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

        min_bed, max_bed = typical_bedtime
        avg_hour = (min_bed.hour + max_bed.hour) / 2
        avg_minute = (min_bed.minute + max_bed.minute) / 2
        return time(int(avg_hour), int(avg_minute))

    # Used by: predict_next_sleep
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

            if wake_hours > max_wake * WAKE_WINDOW_APPROACHING_FACTOR:
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

        if age_months <= 3:
            suggestions.append("At this age, follow baby's cues - patterns will emerge over time")
        elif age_months <= 6:
            suggestions.append("Establish consistent pre-sleep routines for better sleep associations")

        return suggestions[:3]  # Limit to 3 suggestions


# Used by: stats
async def get_schedule_prediction(baby_id: int) -> Dict[str, Any]:
    """Get schedule prediction for baby."""
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
