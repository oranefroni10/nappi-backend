"""
Statistics API Endpoints - Provides data for the Statistics page graphs.

Endpoints:
- GET /stats/sensors - Sensor averages over time (from daily_summary)
- GET /stats/sleep-patterns - Sleep time patterns with clustering (from awakening_events)
- GET /stats/daily-sleep - Daily sleep totals (from awakening_events)
- GET /stats/insights - AI-powered sleep insights from Gemini
"""

import logging
from datetime import date, datetime, timedelta
from typing import List, Literal, Optional
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

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

# Validation constants
MIN_DAYS = 7
MAX_DAYS = 90  # 3 months


def validate_date_range(start_date: date, end_date: date) -> None:
    """Validate date range is within allowed bounds."""
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


async def validate_baby_exists(baby_id: int) -> None:
    """Validate that the baby exists in the database."""
    baby_manager = BabyDataManager()
    exists = await baby_manager.baby_exists(baby_id)
    
    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Baby with id {baby_id} not found"
        )


@router.get("/sensors", response_model=SensorStatsResponse)
async def get_sensor_stats(
    baby_id: int = Query(..., description="Baby ID"),
    sensor: Literal["temperature", "humidity", "noise"] = Query(..., description="Sensor type"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)")
):
    """
    Get sensor averages over a time range for graphing.
    
    Data comes from daily_summary table (one point per day).
    Minimum 7 days, maximum 90 days (3 months).
    """
    # Validate inputs
    validate_date_range(start_date, end_date)
    await validate_baby_exists(baby_id)
    
    # Map sensor name to database column
    sensor_column_map = {
        "temperature": "avg_temp",
        "humidity": "avg_humidity",
        "noise": "avg_noise"
    }
    db_column = sensor_column_map[sensor]
    
    # Fetch data
    baby_manager = BabyDataManager()
    summaries = await baby_manager.get_daily_summaries_range(
        baby_id=baby_id,
        start_date=start_date,
        end_date=end_date
    )
    
    # Build response data points
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


@router.get("/sleep-patterns", response_model=SleepPatternsResponse)
async def get_sleep_patterns(
    baby_id: int = Query(..., description="Baby ID"),
    month: int = Query(None, ge=1, le=12, description="Month (1-12), defaults to current"),
    year: int = Query(None, description="Year, defaults to current")
):
    """
    Get sleep time patterns for a specific month.
    
    Returns clustered sleep time windows with averaged start/end times.
    Useful for parents to understand when the baby typically sleeps.
    """
    # Default to current month/year
    now = datetime.now()
    if month is None:
        month = now.month
    if year is None:
        year = now.year
    
    await validate_baby_exists(baby_id)
    
    # Fetch sleep sessions for the month
    baby_manager = BabyDataManager()
    raw_sessions = await baby_manager.get_sleep_sessions_for_month(
        baby_id=baby_id,
        year=year,
        month=month
    )
    
    # Analyze patterns using clustering
    patterns_data = analyze_sleep_patterns(raw_sessions)
    
    # Convert to Pydantic models
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


@router.get("/daily-sleep", response_model=DailySleepResponse)
async def get_daily_sleep(
    baby_id: int = Query(..., description="Baby ID"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)")
):
    """
    Get total sleep hours per day over a time range.
    
    Returns daily sleep totals and session counts for graphing.
    Minimum 7 days, maximum 90 days (3 months).
    """
    # Validate inputs
    validate_date_range(start_date, end_date)
    await validate_baby_exists(baby_id)
    
    # Fetch sleep sessions
    baby_manager = BabyDataManager()
    sessions = await baby_manager.get_sleep_sessions_for_range(
        baby_id=baby_id,
        start_date=start_date,
        end_date=end_date
    )
    
    # Aggregate raw duration by date (backward compatible)
    daily_data = defaultdict(lambda: {"total_minutes": 0.0, "sessions": 0})

    for session in sessions:
        session_date = session.get("session_date")
        duration = session.get("duration_minutes") or 0.0
        if session_date:
            daily_data[session_date]["total_minutes"] += duration

    # Count sleep blocks per date (grouped, not raw events)
    blocks = group_into_sleep_blocks(sessions, source="sessions_for_range")
    for block in blocks:
        block_date = block.block_end.date()
        daily_data[block_date]["sessions"] += 1
    
    # Build response data points
    data_points = []
    for day_date, stats in sorted(daily_data.items()):
        data_points.append(DailySleepPoint(
            date=day_date,
            total_hours=round(stats["total_minutes"] / 60.0, 2),
            sessions_count=stats["sessions"]
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


@router.get("/insights")
async def get_sleep_insights(
    baby_id: int = Query(..., description="Baby ID"),
    event_id: Optional[int] = Query(None, description="Specific awakening event ID (optional, defaults to latest)")
):
    """
    Get AI-powered insights about a baby's sleep/awakening.
    
    If event_id is provided, analyzes that specific awakening event.
    Otherwise, analyzes the most recent awakening event.
    
    Returns Gemini-generated insights about:
    - Likely causes of awakening
    - Environmental factors that may have affected sleep
    - Actionable tips for better sleep
    """
    await validate_baby_exists(baby_id)
    
    baby_manager = BabyDataManager()
    
    # Get the awakening event
    if event_id:
        event = await baby_manager.get_awakening_event_by_id(event_id, baby_id)
        if not event:
            raise HTTPException(
                status_code=404,
                detail=f"Awakening event {event_id} not found for baby {baby_id}"
            )
    else:
        # Get most recent awakening
        event = await baby_manager.get_latest_awakening_event(baby_id)
        if not event:
            raise HTTPException(
                status_code=404,
                detail=f"No awakening events found for baby {baby_id}"
            )
    
    # Parse event data
    awakened_at = event.get("awakened_at")
    sleep_started_at = event.get("sleep_started_at")
    
    if not awakened_at:
        raise HTTPException(
            status_code=400,
            detail="Awakening event missing awakened_at timestamp"
        )
    
    # Calculate sleep duration
    if sleep_started_at:
        sleep_duration_minutes = (awakened_at - sleep_started_at).total_seconds() / 60.0
    else:
        sleep_duration_minutes = 0.0
    
    # Run correlation analysis with Gemini
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


@router.get("/optimal", response_model=OptimalStatsResponse)
async def get_optimal_stats(
    baby_id: int = Query(..., description="Baby ID")
):
    """
    Get optimal sleep conditions for a baby.
    
    Returns the calculated optimal temperature, humidity, and noise levels
    based on the baby's best sleep sessions.
    
    Returns has_data=False if not enough data has been collected yet.
    """
    await validate_baby_exists(baby_id)
    
    baby_manager = BabyDataManager()
    
    # Query optimal_stats table for this baby
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
    
    # Check if we have meaningful data (at least one value)
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


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    baby_id: int = Query(..., description="Baby ID")
):
    """
    Get comprehensive sleep trend analysis for a baby.
    
    Returns 7-day and 30-day trend analysis with AI-generated insights,
    including sleep quality trends, consistency scores, and age-appropriate
    comparisons.
    """
    await validate_baby_exists(baby_id)
    
    # Get comprehensive trend analysis
    result = await get_sleep_trends(baby_id, include_ai_summary=True)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    # Build response
    response = TrendsResponse(
        baby_id=result["baby_id"],
        baby_name=result["baby_name"],
        age_months=result["age_months"],
        age_recommendation=AgeRecommendation(**result["age_recommendation"])
    )
    
    # Add weekly trend if available
    if result.get("weekly"):
        response.weekly = WeeklyTrend(**result["weekly"])
    
    # Add monthly trend if available
    if result.get("monthly"):
        response.monthly = MonthlyTrend(**result["monthly"])
    
    # Add AI insights if available
    if result.get("ai_insights"):
        response.ai_insights = AITrendInsights(**result["ai_insights"])
    
    logger.info(f"Retrieved trends for baby {baby_id}")
    return response


@router.get("/schedule-prediction", response_model=SchedulePredictionResponse)
async def get_schedule_prediction_endpoint(
    baby_id: int = Query(..., description="Baby ID")
):
    """
    Get schedule prediction for a baby.
    
    Predicts the next likely sleep window based on:
    - Historical sleep patterns
    - Age-appropriate wake windows
    - Time since last awakening
    
    Returns prediction with confidence level and actionable suggestions.
    """
    await validate_baby_exists(baby_id)
    
    # Get schedule prediction
    result = await get_schedule_prediction(baby_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    # Build response
    response = SchedulePredictionResponse(
        baby_id=result["baby_id"],
        generated_at=datetime.fromisoformat(result["generated_at"]),
        wake_window_range_hours=WakeWindowRange(**result["wake_window_range_hours"]),
        optimal_bedtime=result["optimal_bedtime"],
        current_wake_duration_minutes=result.get("current_wake_duration_minutes"),
        suggestions=result.get("suggestions", [])
    )
    
    # Add next sleep prediction if available
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


@router.get("/ai-summary", response_model=AISummaryResponse)
async def get_ai_summary(
    baby_id: int = Query(..., description="Baby ID")
):
    """
    Get comprehensive AI summary for the home dashboard.
    
    Combines multiple AI analyses into a single response:
    - Sleep quality summary
    - Environment assessment
    - Next sleep prediction
    - Today's tip
    - Trend indicator
    - Quick insights
    
    Optimized for display on the home dashboard.
    """
    await validate_baby_exists(baby_id)
    
    baby_manager = BabyDataManager()
    
    # Get baby info
    baby = await baby_manager.get_baby_by_id(baby_id)
    if not baby:
        raise HTTPException(status_code=404, detail="Baby not found")
    
    baby_name = baby.first_name
    now = datetime.now()
    
    # Get latest awakening event for sleep summary
    latest_event = await baby_manager.get_latest_awakening_event(baby_id)
    
    # Build sleep quality summary
    sleep_summary = SleepQualitySummary(
        message="Keep tracking sleep to see insights!"
    )
    
    if latest_event:
        sleep_duration = latest_event.get("sleep_duration_minutes")
        if sleep_duration:
            sleep_hours = sleep_duration / 60.0
            quality = "good" if sleep_hours >= 1.5 else ("fair" if sleep_hours >= 0.75 else "poor")
            sleep_summary = SleepQualitySummary(
                last_sleep_hours=round(sleep_hours, 1),
                last_sleep_quality=quality,
                message=f"{baby_name}'s last sleep was {sleep_hours:.1f} hours"
            )
    
    # Get current room conditions
    last_readings = await baby_manager.get_last_sensor_readings(baby_id)
    
    environment = EnvironmentStatus(
        status="unknown",
        message="No recent sensor data available"
    )
    
    if last_readings:
        temp = last_readings.get("temp_celcius")
        humidity = last_readings.get("humidity")
        noise = last_readings.get("noise_decibel")
        
        issues = []
        temp_status = "optimal"
        humidity_status = "optimal"
        noise_status = "optimal"
        
        if temp:
            if temp > 24:
                temp_status = "high"
                issues.append("temperature is high")
            elif temp < 18:
                temp_status = "low"
                issues.append("temperature is low")
        
        if humidity:
            if humidity > 60:
                humidity_status = "high"
                issues.append("humidity is high")
            elif humidity < 40:
                humidity_status = "low"
                issues.append("humidity is low")
        
        if noise and noise > 50:
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
    
    # Get schedule prediction
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
    
    # Get trend info
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
    
    # Generate today's tip based on available data
    todays_tip = _generate_todays_tip(baby_name, environment, sleep_summary, weekly_trend)
    
    # Generate quick insights
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


@router.get("/insights-enhanced", response_model=EnhancedInsightsResponse)
async def get_enhanced_insights(
    baby_id: int = Query(..., description="Baby ID"),
    event_id: Optional[int] = Query(None, description="Specific awakening event ID (optional)")
):
    """
    Get enhanced AI-powered insights with structured multi-section response.
    
    Returns detailed analysis including:
    - Likely cause of awakening
    - Multiple actionable tips
    - Environment assessment
    - Age-appropriate context
    - Sleep quality note
    """
    await validate_baby_exists(baby_id)
    
    baby_manager = BabyDataManager()
    
    # Get the awakening event
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
    
    # Calculate sleep duration
    if sleep_started_at:
        sleep_duration_minutes = (awakened_at - sleep_started_at).total_seconds() / 60.0
    else:
        sleep_duration_minutes = 0.0
    
    # Run enhanced correlation analysis
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
    
    # Build structured insight response
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


def _generate_todays_tip(
    baby_name: str,
    environment: EnvironmentStatus,
    sleep_summary: SleepQualitySummary,
    weekly_trend: Optional[str]
) -> str:
    """Generate a contextual tip for today."""
    
    # Priority 1: Environment issues
    if environment.status == "needs_attention":
        if environment.temperature_status == "high":
            return f"We noticed the room is a bit warm — {baby_name} might sleep more comfortably if you cool it down to around 18-22°C."
        elif environment.temperature_status == "low":
            return f"The room feels a bit cool for {baby_name}. A sleep sack or a small thermostat adjustment could help."
        elif environment.humidity_status == "low":
            return f"The air seems a little dry — a humidifier in {baby_name}'s room might make things more comfortable."
        elif environment.noise_status == "high":
            return f"We noticed some extra noise in the room. White noise could help mask it for {baby_name}."

    # Priority 2: Sleep quality
    if sleep_summary.last_sleep_quality == "poor":
        return f"Short naps happen — a calming pre-sleep routine might help {baby_name} ease into deeper sleep."

    # Priority 3: Trends
    if weekly_trend == "declining":
        return f"Sleep has been a bit uneven lately — that's normal. Sticking to consistent routines can really help {baby_name}."
    elif weekly_trend == "improving":
        return f"Nice trend this week! Keeping up the consistent schedule seems to be working well for {baby_name}."
    
    # Default tips
    default_tips = [
        f"Consistency is key - try to maintain regular nap and bedtimes for {baby_name}.",
        f"A calm, dark environment signals sleep time to {baby_name}'s brain.",
        f"Watch for {baby_name}'s sleepy cues: yawning, eye rubbing, or fussiness.",
        f"Brief awakenings between sleep cycles are normal for babies.",
    ]
    
    # Use time of day to pick a relevant tip
    hour = datetime.now().hour
    if hour < 12:
        return f"Morning naps often set the tone for the day. Watch for {baby_name}'s early tiredness cues."
    elif hour < 17:
        return default_tips[hour % len(default_tips)]
    else:
        return f"A consistent bedtime routine helps {baby_name} wind down and sleep better through the night."


def _generate_quick_insights(
    baby_name: str,
    sleep_summary: SleepQualitySummary,
    environment: EnvironmentStatus,
    weekly_trend: Optional[str],
    latest_event: Optional[dict]
) -> List[str]:
    """Generate a list of quick insights."""
    insights = []
    
    # Sleep insight
    if sleep_summary.last_sleep_hours:
        if sleep_summary.last_sleep_quality == "good":
            insights.append(f"{baby_name} had a restful {sleep_summary.last_sleep_hours:.1f}h sleep")
        elif sleep_summary.last_sleep_hours < 1:
            insights.append(f"Last nap was brief ({int(sleep_summary.last_sleep_hours * 60)}min) - watch for early tiredness")
    
    # Environment insight
    if environment.status == "optimal":
        insights.append("Room conditions are ideal for sleep")
    elif environment.status == "needs_attention":
        insights.append(f"Room {environment.message.lower()}")
    
    # Trend insight
    if weekly_trend == "improving":
        insights.append("Sleep quality trending upward this week")
    elif weekly_trend == "declining":
        insights.append("Sleep has been a bit variable — small schedule tweaks might help")
    elif weekly_trend == "stable":
        insights.append("Sleep patterns are consistent")
    
    # Time-based insight
    hour = datetime.now().hour
    if hour < 10:
        insights.append("Good morning! Track first nap for pattern insights")
    elif hour >= 19:
        insights.append("Evening wind-down time - dim lights for better melatonin production")
    
    return insights[:4]  # Limit to 4 insights

