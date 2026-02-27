"""
Stats API — sensor history, sleep analytics, AI-powered insights.

Routes (/stats):
  GET /sensors              - Daily sensor averages over a date range
  GET /sleep-patterns       - Clustered sleep patterns for a given month
  GET /daily-sleep          - Daily sleep totals over a date range
  GET /optimal              - Learned optimal room conditions per baby
  GET /trends               - Weekly + monthly trend analysis with optional AI summary
  GET /schedule-prediction  - Next predicted sleep time based on wake windows + patterns
  GET /ai-summary           - Combined dashboard summary (environment, sleep, tip, insights)
  GET /insights             - AI analysis for a specific awakening event
  GET /insights-enhanced    - Structured multi-section AI analysis for an awakening event
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import List, Literal, Optional
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from ..core.settings import settings
from ..core.utils import SENSOR_TO_ENDPOINT_MAP, SENSOR_TO_DB_COLUMN_MAP
from ..core.constants import (
    TEMP_OPTIMAL_HIGH_C, TEMP_OPTIMAL_LOW_C,
    HUMIDITY_OPTIMAL_HIGH_PCT, HUMIDITY_OPTIMAL_LOW_PCT,
    NOISE_ALERT_HIGH_DB, STATS_MIN_DAYS, STATS_MAX_DAYS,
    SENSOR_FETCH_TIMEOUT_SECONDS,
    GEMINI_TIP_TEMPERATURE, GEMINI_TIP_MAX_TOKENS,
)
from ..services.data_miner import HttpSensorSource
from .models import (
    SensorDataPoint,
    SensorStatsResponse,
    SleepPattern,
    SleepPatternsResponse,
    DailySleepPoint,
    DailySleepResponse,
    OptimalStatsResponse,
    TrendsResponse,
    WeeklyTrend,
    MonthlyTrend,
    AITrendInsights,
    AgeRecommendation,
    SchedulePredictionResponse,
    WakeWindowRange,
    NextSleepPrediction,
    AISummaryResponse,
    SleepQualitySummary,
    EnvironmentStatus,
    EnhancedInsightsResponse,
    StructuredInsightResponse,
)
from ..services.babies_data import BabyDataManager
from ..services.sleep_patterns import analyze_sleep_patterns
from ..services.correlation_analyzer import CorrelationAnalyzer
from ..services.trend_analyzer import get_sleep_trends, get_age_recommendation
from ..services.schedule_predictor import get_schedule_prediction
from ..utils.sleep_blocks import group_into_sleep_blocks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["statistics"])

# Validation constants from STATS_MIN_DAYS / STATS_MAX_DAYS
MIN_DAYS = STATS_MIN_DAYS
MAX_DAYS = STATS_MAX_DAYS


# Used by: get_sensor_stats, get_daily_sleep — 7–90 day bounds
def validate_date_range(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date must be after start_date"
        )

    days_diff = (end_date - start_date).days

    if days_diff < MIN_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range must be at least {MIN_DAYS} days"
        )

    if days_diff > MAX_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range cannot exceed {MAX_DAYS} days (3 months)"
        )


# Used by: all stats endpoints — baby existence check
async def validate_baby_exists(baby_id: int) -> None:
    baby_manager = BabyDataManager()
    exists = await baby_manager.baby_exists(baby_id)

    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Baby with id {baby_id} not found"
        )


# Used by: Statistics page — sensor averages chart
@router.get("/sensors", response_model=SensorStatsResponse)
async def get_sensor_stats(
    baby_id: int = Query(..., description="Baby ID"),
    sensor: Literal["temperature", "humidity", "noise"] = Query(..., description="Sensor type"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)")
):
    validate_date_range(start_date, end_date)
    await validate_baby_exists(baby_id)

    sensor_column_map = {
        "temperature": "avg_temp",
        "humidity": "avg_humidity",
        "noise": "avg_noise"
    }
    db_column = sensor_column_map[sensor]

    baby_manager = BabyDataManager()
    summaries = await baby_manager.get_daily_summaries_range(
        baby_id=baby_id,
        start_date=start_date,
        end_date=end_date
    )

    data_points = []
    for summary in summaries:
        value = summary.get(db_column)
        if value is not None:
            data_points.append(SensorDataPoint(
                date=summary["summary_date"],
                value=round(value, 2)
            ))

    logger.info(
        f"Retrieved {len(data_points)} sensor data points for baby {baby_id} "
        f"({sensor}, {start_date} to {end_date})"
    )

    return SensorStatsResponse(
        baby_id=baby_id,
        sensor=sensor,
        start_date=start_date,
        end_date=end_date,
        data=data_points
    )


# Used by: Statistics page — sleep pattern clusters
@router.get("/sleep-patterns", response_model=SleepPatternsResponse)
async def get_sleep_patterns(
    baby_id: int = Query(..., description="Baby ID"),
    month: int = Query(None, ge=1, le=12, description="Month (1-12), defaults to current"),
    year: int = Query(None, description="Year, defaults to current")
):
    now = datetime.now()
    if month is None:
        month = now.month
    if year is None:
        year = now.year

    await validate_baby_exists(baby_id)

    baby_manager = BabyDataManager()
    raw_sessions = await baby_manager.get_sleep_sessions_for_month(
        baby_id=baby_id,
        year=year,
        month=month
    )

    patterns_data = analyze_sleep_patterns(raw_sessions)

    patterns = [
        SleepPattern(
            cluster_id=p["cluster_id"],
            label=p["label"],
            avg_start=p["avg_start"],
            avg_end=p["avg_end"],
            avg_duration_hours=p["avg_duration_hours"],
            session_count=p["session_count"],
            earliest_start=p["earliest_start"],
            latest_end=p["latest_end"]
        )
        for p in patterns_data
    ]

    total_sessions = sum(p.session_count for p in patterns)

    logger.info(
        f"Analyzed {total_sessions} sleep sessions for baby {baby_id} "
        f"({year}-{month:02d}), found {len(patterns)} patterns"
    )

    return SleepPatternsResponse(
        baby_id=baby_id,
        month=month,
        year=year,
        total_sessions=total_sessions,
        patterns=patterns
    )


# Used by: Statistics page — daily sleep totals
@router.get("/daily-sleep", response_model=DailySleepResponse)
async def get_daily_sleep(
    baby_id: int = Query(..., description="Baby ID"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)")
):
    validate_date_range(start_date, end_date)
    await validate_baby_exists(baby_id)

    baby_manager = BabyDataManager()
    sessions = await baby_manager.get_sleep_sessions_for_range(
        baby_id=baby_id,
        start_date=start_date,
        end_date=end_date
    )

    # Aggregate raw duration by date
    daily_data = defaultdict(lambda: {"total_minutes": 0.0, "sessions": 0, "awakenings": 0})

    for session in sessions:
        session_date = session.get("session_date")
        duration = session.get("duration_minutes") or 0.0
        if session_date:
            daily_data[session_date]["total_minutes"] += duration

    # Count blocks/awakenings per date (grouped, not raw events)
    blocks = group_into_sleep_blocks(sessions, source="sessions_for_range")
    for block in blocks:
        block_date = block.block_end.date()
        daily_data[block_date]["sessions"] += 1
        daily_data[block_date]["awakenings"] += block.interruption_count

    data_points = []
    for day_date, stats in sorted(daily_data.items()):
        data_points.append(DailySleepPoint(
            date=day_date,
            total_hours=round(stats["total_minutes"] / 60.0, 2),
            sessions_count=stats["sessions"],
            awakenings_count=stats["awakenings"]
        ))

    logger.info(
        f"Retrieved daily sleep data for baby {baby_id}: "
        f"{len(data_points)} days with data ({start_date} to {end_date})"
    )

    return DailySleepResponse(
        baby_id=baby_id,
        start_date=start_date,
        end_date=end_date,
        data=data_points
    )


# Used by: Statistics page — AI awakening insights (Gemini)
@router.get("/insights")
async def get_sleep_insights(
    baby_id: int = Query(..., description="Baby ID"),
    event_id: Optional[int] = Query(None, description="Specific awakening event ID (optional, defaults to latest)")
):
    await validate_baby_exists(baby_id)

    baby_manager = BabyDataManager()

    if event_id:
        event = await baby_manager.get_awakening_event_by_id(event_id, baby_id)
        if not event:
            raise HTTPException(
                status_code=404,
                detail=f"Awakening event {event_id} not found for baby {baby_id}"
            )
    else:
        event = await baby_manager.get_latest_awakening_event(baby_id)
        if not event:
            raise HTTPException(
                status_code=404,
                detail=f"No awakening events found for baby {baby_id}"
            )

    awakened_at = event.get("awakened_at")
    sleep_started_at = event.get("sleep_started_at")

    if not awakened_at:
        raise HTTPException(
            status_code=400,
            detail="Awakening event missing awakened_at timestamp"
        )

    if sleep_started_at:
        sleep_duration_minutes = (awakened_at - sleep_started_at).total_seconds() / 60.0
    else:
        sleep_duration_minutes = 0.0

    analyzer = CorrelationAnalyzer()
    result = await analyzer.analyze_awakening(
        baby_id=baby_id,
        awakened_at=awakened_at,
        sleep_duration_minutes=sleep_duration_minutes
    )

    if not result.success:
        logger.warning(f"Insights generation failed for baby {baby_id}: {result.error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate insights: {result.error}"
        )

    logger.info(f"Generated AI insights for baby {baby_id}, event {event.get('id')}")

    return {
        "baby_id": baby_id,
        "event_id": event.get("id"),
        "awakened_at": awakened_at.isoformat() if awakened_at else None,
        "sleep_duration_minutes": round(sleep_duration_minutes, 2),
        "environmental_changes": result.parameters,
        "insights": result.insights,
        "correlation_id": result.correlation_id
    }


# Used by: Home Dashboard — optimal conditions card
@router.get("/optimal", response_model=OptimalStatsResponse)
async def get_optimal_stats(
    baby_id: int = Query(..., description="Baby ID")
):
    await validate_baby_exists(baby_id)

    baby_manager = BabyDataManager()
    optimal = await baby_manager.get_optimal_stats(baby_id)

    if not optimal:
        logger.info(f"No optimal stats found for baby {baby_id}")
        return OptimalStatsResponse(
            baby_id=baby_id,
            temperature=None,
            humidity=None,
            noise=None,
            has_data=False
        )

    has_data = any([
        optimal.get("temperature") is not None,
        optimal.get("humidity") is not None,
        optimal.get("noise") is not None
    ])

    logger.info(f"Retrieved optimal stats for baby {baby_id}: has_data={has_data}")

    return OptimalStatsResponse(
        baby_id=baby_id,
        temperature=optimal.get("temperature"),
        humidity=optimal.get("humidity"),
        noise=optimal.get("noise"),
        has_data=has_data
    )


# Used by: Statistics page — trend analysis
@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    baby_id: int = Query(..., description="Baby ID")
):
    await validate_baby_exists(baby_id)

    result = await get_sleep_trends(baby_id, include_ai_summary=True)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    response = TrendsResponse(
        baby_id=result["baby_id"],
        baby_name=result["baby_name"],
        age_months=result["age_months"],
        age_recommendation=AgeRecommendation(**result["age_recommendation"])
    )

    if result.get("weekly"):
        response.weekly = WeeklyTrend(**result["weekly"])

    if result.get("monthly"):
        response.monthly = MonthlyTrend(**result["monthly"])

    if result.get("ai_insights"):
        response.ai_insights = AITrendInsights(**result["ai_insights"])

    logger.info(f"Retrieved trends for baby {baby_id}")
    return response


# Used by: Home Dashboard — next sleep prediction
@router.get("/schedule-prediction", response_model=SchedulePredictionResponse)
async def get_schedule_prediction_endpoint(
    baby_id: int = Query(..., description="Baby ID")
):
    await validate_baby_exists(baby_id)

    result = await get_schedule_prediction(baby_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    response = SchedulePredictionResponse(
        baby_id=result["baby_id"],
        generated_at=datetime.fromisoformat(result["generated_at"]),
        wake_window_range_hours=WakeWindowRange(**result["wake_window_range_hours"]),
        optimal_bedtime=result["optimal_bedtime"],
        current_wake_duration_minutes=result.get("current_wake_duration_minutes"),
        suggestions=result.get("suggestions", [])
    )

    if result.get("next_sleep"):
        ns = result["next_sleep"]
        response.next_sleep = NextSleepPrediction(
            predicted_time=datetime.fromisoformat(ns["predicted_time"]),
            predicted_time_formatted=ns["predicted_time_formatted"],
            confidence=ns["confidence"],
            type=ns["type"],
            based_on=ns["based_on"],
            minutes_until=ns["minutes_until"],
            wake_window_status=ns["wake_window_status"]
        )

    logger.info(f"Generated schedule prediction for baby {baby_id}")
    return response


# Used by: Home Dashboard — AI summary
@router.get("/ai-summary", response_model=AISummaryResponse)
async def get_ai_summary(
    baby_id: int = Query(..., description="Baby ID")
):
    await validate_baby_exists(baby_id)

    baby_manager = BabyDataManager()

    baby = await baby_manager.get_baby_by_id(baby_id)
    if not baby:
        raise HTTPException(status_code=404, detail="Baby not found")

    baby_name = baby.first_name
    now = datetime.now()

    latest_event = await baby_manager.get_latest_awakening_event(baby_id)

    sleep_summary = SleepQualitySummary(
        message="Keep tracking sleep to see insights!"
    )

    if latest_event:
        sleep_duration = latest_event.get("sleep_duration_minutes")
        if sleep_duration:
            sleep_hours = sleep_duration / 60.0
            sleep_summary = SleepQualitySummary(
                last_sleep_hours=round(sleep_hours, 1),
                message=f"{baby_name}'s last sleep was {sleep_hours:.1f} hours"
            )

    # Live sensors first, fallback to DB
    live_data = {}
    try:
        data_source = HttpSensorSource(
            base_url=settings.SENSOR_API_BASE_URL,
            endpoint_map=SENSOR_TO_ENDPOINT_MAP,
            timeout_seconds=SENSOR_FETCH_TIMEOUT_SECONDS,
        )
        sensor_names = list(SENSOR_TO_ENDPOINT_MAP.keys())
        results = await asyncio.gather(
            *[data_source.get_sensor_data(sensor, baby_id) for sensor in sensor_names],
            return_exceptions=True,
        )
        for sensor_name, result in zip(sensor_names, results):
            if result and not isinstance(result, Exception) and isinstance(result, dict) and "value" in result:
                db_column = SENSOR_TO_DB_COLUMN_MAP.get(sensor_name)
                if db_column:
                    live_data[db_column] = result["value"]
    except Exception as e:
        logger.warning(f"Live sensor fetch failed for ai-summary baby {baby_id}: {e}")

    if not live_data:
        last_readings = await baby_manager.get_last_sensor_readings(baby_id)
        if last_readings:
            live_data = last_readings

    environment = EnvironmentStatus(
        status="unknown",
        message="No recent sensor data available"
    )

    if live_data:
        temp = live_data.get("temp_celcius")
        humidity = live_data.get("humidity")
        noise = live_data.get("noise_decibel")

        issues = []
        temp_status = "optimal"
        humidity_status = "optimal"
        noise_status = "optimal"

        if temp:
            if temp > TEMP_OPTIMAL_HIGH_C:
                temp_status = "high"
                issues.append("temperature is high")
            elif temp < TEMP_OPTIMAL_LOW_C:
                temp_status = "low"
                issues.append("temperature is low")

        if humidity:
            if humidity > HUMIDITY_OPTIMAL_HIGH_PCT:
                humidity_status = "high"
                issues.append("humidity is high")
            elif humidity < HUMIDITY_OPTIMAL_LOW_PCT:
                humidity_status = "low"
                issues.append("humidity is low")

        if noise and noise > NOISE_ALERT_HIGH_DB:
            noise_status = "high"
            issues.append("noise level is elevated")

        if issues:
            environment = EnvironmentStatus(
                status="needs_attention",
                temperature_status=temp_status,
                humidity_status=humidity_status,
                noise_status=noise_status,
                message=f"Room {', '.join(issues)}"
            )
        else:
            environment = EnvironmentStatus(
                status="optimal",
                temperature_status=temp_status,
                humidity_status=humidity_status,
                noise_status=noise_status,
                message="Room conditions are ideal for sleep"
            )

    try:
        schedule_result = await get_schedule_prediction(baby_id)
        next_sleep_prediction = None
        next_sleep_time = None

        if schedule_result.get("next_sleep"):
            ns = schedule_result["next_sleep"]
            next_sleep_time = ns["predicted_time_formatted"]
            minutes = ns["minutes_until"]
            if minutes < 60:
                next_sleep_prediction = f"Next sleep in about {minutes} minutes"
            else:
                hours = minutes // 60
                next_sleep_prediction = f"Next sleep in about {hours} hour{'s' if hours > 1 else ''}"
    except:
        next_sleep_prediction = None
        next_sleep_time = None

    try:
        trend_result = await get_sleep_trends(baby_id, include_ai_summary=False)
        weekly_trend = None
        trend_message = None

        if trend_result.get("weekly"):
            weekly = trend_result["weekly"]
            weekly_trend = weekly.get("trend")
            if weekly_trend == "improving":
                trend_message = "Sleep quality is improving this week!"
            elif weekly_trend == "declining":
                trend_message = "Sleep has been a bit challenging this week"
            else:
                trend_message = "Sleep patterns are stable"
    except:
        weekly_trend = None
        trend_message = None

    todays_tip = await _generate_todays_tip(baby_name, environment, sleep_summary, weekly_trend)

    quick_insights = _generate_quick_insights(
        baby_name,
        sleep_summary,
        environment,
        weekly_trend,
        latest_event
    )

    return AISummaryResponse(
        baby_id=baby_id,
        baby_name=baby_name,
        generated_at=now,
        sleep_summary=sleep_summary,
        environment=environment,
        next_sleep_prediction=next_sleep_prediction,
        next_sleep_time=next_sleep_time,
        todays_tip=todays_tip,
        weekly_trend=weekly_trend,
        trend_message=trend_message,
        quick_insights=quick_insights
    )


# Used by: Statistics page — enhanced AI insights
@router.get("/insights-enhanced", response_model=EnhancedInsightsResponse)
async def get_enhanced_insights(
    baby_id: int = Query(..., description="Baby ID"),
    event_id: Optional[int] = Query(None, description="Specific awakening event ID (optional)")
):
    await validate_baby_exists(baby_id)

    baby_manager = BabyDataManager()

    if event_id:
        event = await baby_manager.get_awakening_event_by_id(event_id, baby_id)
        if not event:
            raise HTTPException(
                status_code=404,
                detail=f"Awakening event {event_id} not found for baby {baby_id}"
            )
    else:
        event = await baby_manager.get_latest_awakening_event(baby_id)
        if not event:
            raise HTTPException(
                status_code=404,
                detail=f"No awakening events found for baby {baby_id}"
            )

    awakened_at = event.get("awakened_at")
    sleep_started_at = event.get("sleep_started_at")

    if not awakened_at:
        raise HTTPException(
            status_code=400,
            detail="Awakening event missing awakened_at timestamp"
        )

    if sleep_started_at:
        sleep_duration_minutes = (awakened_at - sleep_started_at).total_seconds() / 60.0
    else:
        sleep_duration_minutes = 0.0

    analyzer = CorrelationAnalyzer()
    result = await analyzer.analyze_awakening_enhanced(
        baby_id=baby_id,
        awakened_at=awakened_at,
        sleep_duration_minutes=sleep_duration_minutes
    )

    if not result.success:
        logger.warning(f"Enhanced insights generation failed for baby {baby_id}: {result.error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate enhanced insights: {result.error}"
        )

    structured_insight = None
    if result.insights:
        structured_insight = StructuredInsightResponse(
            likely_cause=result.insights.likely_cause,
            actionable_tips=result.insights.actionable_tips,
            environment_assessment=result.insights.environment_assessment,
            age_context=result.insights.age_context,
            sleep_quality_note=result.insights.sleep_quality_note
        )

    logger.info(f"Generated enhanced insights for baby {baby_id}")

    return EnhancedInsightsResponse(
        baby_id=baby_id,
        event_id=event.get("id"),
        awakened_at=awakened_at,
        sleep_duration_minutes=round(sleep_duration_minutes, 2),
        environmental_changes=result.parameters,
        insights=structured_insight,
        simple_insight=result.simple_insight,
        correlation_id=result.correlation_id
    )


# Used by: get_ai_summary — daily tip via Gemini
async def _generate_todays_tip(
    baby_name: str,
    environment: EnvironmentStatus,
    sleep_summary: SleepQualitySummary,
    weekly_trend: Optional[str]
) -> str:
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None
        if not client:
            return _fallback_tip(baby_name)

        context_parts = [f"Baby name: {baby_name}"]

        if environment.status == "needs_attention":
            issues = []
            if environment.temperature_status == "high":
                issues.append("room temperature is too high")
            elif environment.temperature_status == "low":
                issues.append("room temperature is too low")
            if environment.humidity_status == "low":
                issues.append("humidity is low")
            elif environment.humidity_status == "high":
                issues.append("humidity is high")
            if environment.noise_status == "high":
                issues.append("noise level is elevated")
            if issues:
                context_parts.append(f"Room issues: {', '.join(issues)}")
        else:
            context_parts.append("Room conditions: optimal")

        if sleep_summary.last_sleep_hours is not None:
            context_parts.append(f"Last sleep duration: {sleep_summary.last_sleep_hours:.1f} hours")
        if sleep_summary.trend_direction:
            context_parts.append(f"Sleep trend direction: {sleep_summary.trend_direction}")

        if weekly_trend:
            context_parts.append(f"Weekly sleep trend: {weekly_trend}")

        hour = datetime.now().hour
        if hour < 12:
            context_parts.append("Time of day: morning")
        elif hour < 17:
            context_parts.append("Time of day: afternoon")
        else:
            context_parts.append("Time of day: evening")

        context = "\n".join(context_parts)

        prompt = f"""You are a gentle, supportive pediatric sleep consultant for a baby monitoring app.

Based on the following context, generate ONE short, personalized daily tip for the parent.

{context}

Rules:
- 1-2 sentences maximum
- Use the baby's name naturally
- Be warm and reassuring, never alarming
- Use soft language: "you might want to", "it could help", "we noticed"
- If there's a room issue, prioritize that. Otherwise focus on sleep quality or general advice relevant to the time of day.
- Do NOT use emojis
- Make it feel personal and specific to the current situation, not generic"""

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=settings.GEMINI_MODEL_CHAT,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=GEMINI_TIP_TEMPERATURE, max_output_tokens=GEMINI_TIP_MAX_TOKENS)
            )
        )

        if response and response.text:
            tip = response.text.strip().strip('"')
            if tip:
                return tip

    except Exception as e:
        logger.warning(f"Gemini tip generation failed, using fallback: {e}")

    return _fallback_tip(baby_name)


def _fallback_tip(baby_name: str) -> str:
    hour = datetime.now().hour
    if hour < 12:
        return f"Morning naps often set the tone for the day. Watch for {baby_name}'s early tiredness cues."
    elif hour < 17:
        return f"A calm, dark environment signals sleep time to {baby_name}'s brain."
    else:
        return f"A consistent bedtime routine helps {baby_name} wind down and sleep better through the night."


# Used by: get_ai_summary — quick insight strings
def _generate_quick_insights(
    baby_name: str,
    sleep_summary: SleepQualitySummary,
    environment: EnvironmentStatus,
    weekly_trend: Optional[str],
    latest_event: Optional[dict]
) -> List[str]:
    insights = []

    if sleep_summary.last_sleep_hours:
        if sleep_summary.last_sleep_hours is not None and sleep_summary.last_sleep_hours >= 1.5:
            insights.append(f"{baby_name} had a restful {sleep_summary.last_sleep_hours:.1f}h sleep")
        elif sleep_summary.last_sleep_hours < 1:
            insights.append(f"Last nap was brief ({int(sleep_summary.last_sleep_hours * 60)}min) - watch for early tiredness")

    if environment.status == "optimal":
        insights.append("Room conditions are ideal for sleep")
    elif environment.status == "needs_attention":
        insights.append(f"Room {environment.message.lower()}")

    if weekly_trend == "improving":
        insights.append("Sleep quality trending upward this week")
    elif weekly_trend == "declining":
        insights.append("Sleep has been a bit variable — small schedule tweaks might help")
    elif weekly_trend == "stable":
        insights.append("Sleep patterns are consistent")

    hour = datetime.now().hour
    if hour < 10:
        insights.append("Good morning! Track first nap for pattern insights")
    elif hour >= 19:
        insights.append("Evening wind-down time - dim lights for better melatonin production")

    return insights[:4]  # cap for dashboard display
