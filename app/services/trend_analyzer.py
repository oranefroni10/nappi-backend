"""Analyzes sleep trends over time and generates AI insights."""

import logging
import asyncio
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from statistics import mean, stdev

from .babies_data import BabyDataManager
from ..core.settings import settings
from ..core.constants import (
    AGE_SLEEP_RECOMMENDATIONS, DAYS_PER_MONTH,
    TREND_IMPROVING_THRESHOLD_PCT, TREND_DECLINING_THRESHOLD_PCT,
    CONSISTENCY_STD_DEV_MULTIPLIER,
    GEMINI_TRENDS_TEMPERATURE, GEMINI_TRENDS_MAX_TOKENS,
)
from ..utils.sleep_blocks import group_into_sleep_blocks

logger = logging.getLogger(__name__)

_gemini_client = None


# Used by: TrendAnalyzer.generate_ai_summary()
def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None and settings.GEMINI_API_KEY:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            logger.info("Gemini client initialized for trend analyzer")
        except ImportError:
            logger.warning("google-genai package not installed")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
    return _gemini_client


# Used by: TrendAnalyzer.generate_ai_summary(), get_sleep_trends()
def get_age_recommendation(age_months: int) -> Dict[str, Any]:
    for (min_age, max_age), recommendations in AGE_SLEEP_RECOMMENDATIONS.items():
        if min_age <= age_months <= max_age:
            return recommendations
    return {"min_hours": 10, "max_hours": 12, "typical_naps": "0-1", "night_hours": "10-11"}


@dataclass
class DailyStats:
    date: date
    total_sleep_hours: float
    session_count: int
    avg_temp: Optional[float]
    avg_humidity: Optional[float]
    avg_noise: Optional[float]


@dataclass
class TrendResult:
    period_days: int
    avg_sleep_hours: float
    sleep_trend: str  # "improving", "declining", "stable"
    trend_percentage: float
    consistency_score: float  # 0-100
    best_day: Optional[str]
    worst_day: Optional[str]
    total_sessions: int
    avg_sessions_per_day: float
    daily_data: List[DailyStats]


@dataclass
class AITrendInsight:
    summary: str
    highlights: List[str]
    concerns: List[str]
    recommendations: List[str]
    age_comparison: str


class TrendAnalyzer:

    def __init__(self):
        self.baby_manager = BabyDataManager()

    # Used by: get_sleep_trends() — 7-day and 30-day trend analysis
    async def analyze_trends(
        self,
        baby_id: int,
        days: int = 7
    ) -> Optional[TrendResult]:
        logger.info(f"Analyzing {days}-day trends for baby {baby_id}")
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        sessions = await self.baby_manager.get_sleep_sessions_for_range(
            baby_id=baby_id,
            start_date=start_date,
            end_date=end_date
        )
        
        if not sessions:
            logger.warning(f"No sleep sessions found for baby {baby_id}")
            return None
        
        summaries = await self.baby_manager.get_daily_summaries_range(
            baby_id=baby_id,
            start_date=start_date,
            end_date=end_date
        )
        
        daily_data = self._aggregate_daily_data(sessions, summaries)
        
        if len(daily_data) < 2:
            logger.warning(f"Insufficient daily data for trend analysis: {len(daily_data)} days")
            return None
        
        sleep_hours = [d.total_sleep_hours for d in daily_data if d.total_sleep_hours > 0]
        
        if len(sleep_hours) < 2:
            return None
        
        avg_sleep = mean(sleep_hours)
        
        # Trend direction: split period in half, compare avg sleep. >5% = improving, <-5% = declining.
        mid_point = len(sleep_hours) // 2
        first_half_avg = mean(sleep_hours[:mid_point]) if mid_point > 0 else avg_sleep
        second_half_avg = mean(sleep_hours[mid_point:]) if mid_point < len(sleep_hours) else avg_sleep

        trend_diff = second_half_avg - first_half_avg
        trend_percentage = (trend_diff / first_half_avg * 100) if first_half_avg > 0 else 0

        if trend_percentage > TREND_IMPROVING_THRESHOLD_PCT:
            sleep_trend = "improving"
        elif trend_percentage < TREND_DECLINING_THRESHOLD_PCT:
            sleep_trend = "declining"
        else:
            sleep_trend = "stable"

        # Consistency score (0-100): lower std_dev of daily hours = higher score.
        if len(sleep_hours) >= 2:
            try:
                std_dev = stdev(sleep_hours)
                consistency_score = max(0, min(100, 100 - (std_dev * CONSISTENCY_STD_DEV_MULTIPLIER)))
            except:
                consistency_score = 50.0
        else:
            consistency_score = 50.0
        
        sorted_days = sorted(daily_data, key=lambda x: x.total_sleep_hours, reverse=True)
        best_day = sorted_days[0].date.strftime("%A") if sorted_days else None
        worst_day = sorted_days[-1].date.strftime("%A") if sorted_days else None
        
        total_sessions = sum(d.session_count for d in daily_data)
        days_with_data = len([d for d in daily_data if d.session_count > 0])
        avg_sessions = total_sessions / days_with_data if days_with_data > 0 else 0
        
        return TrendResult(
            period_days=days,
            avg_sleep_hours=round(avg_sleep, 2),
            sleep_trend=sleep_trend,
            trend_percentage=round(abs(trend_percentage), 1),
            consistency_score=round(consistency_score, 1),
            best_day=best_day,
            worst_day=worst_day,
            total_sessions=total_sessions,
            avg_sessions_per_day=round(avg_sessions, 1),
            daily_data=daily_data
        )

    # Used by: self.analyze_trends() — aggregates sessions + summaries by date
    def _aggregate_daily_data(
        self,
        sessions: List[Dict[str, Any]],
        summaries: List[Dict[str, Any]]
    ) -> List[DailyStats]:
        from collections import defaultdict

        summary_by_date = {s["summary_date"]: s for s in summaries}

        daily_sleep = defaultdict(lambda: {"total_minutes": 0.0, "block_count": 0})

        for session in sessions:
            session_date = session.get("session_date")
            duration = session.get("duration_minutes") or 0.0
            if session_date:
                daily_sleep[session_date]["total_minutes"] += duration

        blocks = group_into_sleep_blocks(sessions, source="sessions_for_range")
        for block in blocks:
            block_date = block.block_end.date()
            if block_date in daily_sleep:
                daily_sleep[block_date]["block_count"] += 1
            else:
                daily_sleep[block_date]["block_count"] += 1

        daily_data = []
        for day_date, stats in sorted(daily_sleep.items()):
            summary = summary_by_date.get(day_date, {})

            daily_data.append(DailyStats(
                date=day_date,
                total_sleep_hours=round(stats["total_minutes"] / 60.0, 2),
                session_count=stats["block_count"],
                avg_temp=summary.get("avg_temp"),
                avg_humidity=summary.get("avg_humidity"),
                avg_noise=summary.get("avg_noise")
            ))

        return daily_data

    # Used by: get_sleep_trends() — AI-powered weekly/monthly summary
    async def generate_ai_summary(
        self,
        baby_id: int,
        trend_7d: Optional[TrendResult],
        trend_30d: Optional[TrendResult],
        baby_age_months: int,
        baby_name: str
    ) -> Optional[AITrendInsight]:
        client = _get_gemini_client()
        
        if not client:
            logger.warning("Gemini client not available for trend summary")
            return None
        
        age_rec = get_age_recommendation(baby_age_months)
        
        prompt = self._build_trend_prompt(
            baby_name=baby_name,
            age_months=baby_age_months,
            trend_7d=trend_7d,
            trend_30d=trend_30d,
            age_rec=age_rec
        )
        
        try:
            from google.genai import types
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=settings.GEMINI_MODEL_INSIGHTS,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=GEMINI_TRENDS_TEMPERATURE,
                        max_output_tokens=GEMINI_TRENDS_MAX_TOKENS,
                    ),
                )
            )
            
            if response and response.text:
                return self._parse_ai_response(response.text.strip(), baby_age_months, age_rec)
            
        except Exception as e:
            logger.error(f"Failed to generate AI trend summary: {e}")
        
        return None

    # Used by: self.generate_ai_summary() — builds Gemini prompt
    def _build_trend_prompt(
        self,
        baby_name: str,
        age_months: int,
        trend_7d: Optional[TrendResult],
        trend_30d: Optional[TrendResult],
        age_rec: Dict[str, Any]
    ) -> str:
        age_str = self._format_age(age_months)
        
        weekly_section = ""
        if trend_7d:
            weekly_section = f"""
## This Week (Last 7 Days)
- Average sleep: {trend_7d.avg_sleep_hours} hours/day
- Trend: {trend_7d.sleep_trend} ({trend_7d.trend_percentage}% change)
- Consistency score: {trend_7d.consistency_score}/100
- Total naps/sleep sessions: {trend_7d.total_sessions}
- Average sessions per day: {trend_7d.avg_sessions_per_day}
- Best day: {trend_7d.best_day}
- Most challenging day: {trend_7d.worst_day}
"""
        else:
            weekly_section = "\n## This Week: Not enough data yet\n"
        
        monthly_section = ""
        if trend_30d:
            monthly_section = f"""
## This Month (Last 30 Days)
- Average sleep: {trend_30d.avg_sleep_hours} hours/day
- Trend: {trend_30d.sleep_trend} ({trend_30d.trend_percentage}% change)
- Consistency score: {trend_30d.consistency_score}/100
- Total sessions: {trend_30d.total_sessions}
"""
        else:
            monthly_section = "\n## This Month: Not enough data yet\n"
        
        prompt = f"""You are a pediatric sleep consultant analyzing sleep data for {baby_name}, a {age_str} baby.

## Age-Appropriate Guidelines
- Recommended daily sleep: {age_rec['min_hours']}-{age_rec['max_hours']} hours
- Typical naps at this age: {age_rec['typical_naps']} per day
- Night sleep expectation: {age_rec['night_hours']} hours
{weekly_section}{monthly_section}
## Your Task
Provide a structured analysis with these EXACT sections:

SUMMARY: (2-3 sentences overall assessment)

HIGHLIGHTS: (2-3 positive observations, one per line starting with "- ")

THINGS_TO_WATCH: (1-2 areas worth keeping an eye on, or "None" if everything looks good, one per line starting with "- ")

SUGGESTIONS: (2-3 gentle, actionable tips framed as options — e.g., "you might try...", one per line starting with "- ")

AGE_COMPARISON: (1 sentence comparing to typical babies this age)

Be warm, supportive, and practical. Frame suggestions as options, not orders. Avoid dramatic language — baby sleep varies greatly and small changes are normal."""

        return prompt

    # Used by: self.generate_ai_summary() — parses Gemini response into structured insight
    def _parse_ai_response(
        self,
        response_text: str,
        age_months: int,
        age_rec: Dict[str, Any]
    ) -> AITrendInsight:
        summary = ""
        highlights = []
        concerns = []
        recommendations = []
        age_comparison = ""
        
        current_section = None
        
        for line in response_text.split('\n'):
            line = line.strip()
            
            if line.startswith("SUMMARY:"):
                current_section = "summary"
                summary = line.replace("SUMMARY:", "").strip()
            elif line.startswith("HIGHLIGHTS:"):
                current_section = "highlights"
            elif line.startswith("THINGS_TO_WATCH:") or line.startswith("CONCERNS:"):
                current_section = "concerns"
            elif line.startswith("SUGGESTIONS:") or line.startswith("RECOMMENDATIONS:"):
                current_section = "recommendations"
            elif line.startswith("AGE_COMPARISON:"):
                current_section = "age_comparison"
                age_comparison = line.replace("AGE_COMPARISON:", "").strip()
            elif line.startswith("- "):
                item = line[2:].strip()
                if current_section == "highlights":
                    highlights.append(item)
                elif current_section == "concerns":
                    if item.lower() != "none":
                        concerns.append(item)
                elif current_section == "recommendations":
                    recommendations.append(item)
            elif current_section == "summary" and line and not line.startswith("-"):
                summary += " " + line
            elif current_section == "age_comparison" and line and not line.startswith("-"):
                age_comparison += " " + line
        
        if not summary:
            summary = response_text[:200] if response_text else "Analysis in progress."
        
        return AITrendInsight(
            summary=summary.strip(),
            highlights=highlights[:3],
            concerns=concerns[:2],
            recommendations=recommendations[:3],
            age_comparison=age_comparison.strip() or f"Sleep patterns are being compared to typical {self._format_age(age_months)} babies."
        )

    # Used by: self._build_trend_prompt(), self._parse_ai_response()
    def _format_age(self, age_months: int) -> str:
        if age_months < 1:
            return "newborn"
        elif age_months == 1:
            return "1 month old"
        elif age_months < 12:
            return f"{age_months} months old"
        elif age_months == 12:
            return "1 year old"
        else:
            years = age_months // 12
            months = age_months % 12
            if months == 0:
                return f"{years} year{'s' if years > 1 else ''} old"
            return f"{years} year{'s' if years > 1 else ''} and {months} month{'s' if months > 1 else ''} old"


# Used by: stats.py (GET /stats/trends, GET /stats/ai-summary)
async def get_sleep_trends(
    baby_id: int,
    include_ai_summary: bool = True
) -> Dict[str, Any]:
    analyzer = TrendAnalyzer()
    
    baby = await analyzer.baby_manager.get_baby_by_id(baby_id)
    if not baby:
        return {"error": "Baby not found"}
    
    today = date.today()
    age_days = (today - baby.birthdate).days
    age_months = age_days // DAYS_PER_MONTH
    
    trend_7d = await analyzer.analyze_trends(baby_id, days=7)
    trend_30d = await analyzer.analyze_trends(baby_id, days=30)
    
    result = {
        "baby_id": baby_id,
        "baby_name": baby.first_name,
        "age_months": age_months,
        "age_recommendation": get_age_recommendation(age_months),
    }
    
    if trend_7d:
        result["weekly"] = {
            "avg_sleep_hours": trend_7d.avg_sleep_hours,
            "trend": trend_7d.sleep_trend,
            "trend_percentage": trend_7d.trend_percentage,
            "consistency_score": trend_7d.consistency_score,
            "total_sessions": trend_7d.total_sessions,
            "avg_sessions_per_day": trend_7d.avg_sessions_per_day,
            "best_day": trend_7d.best_day,
            "worst_day": trend_7d.worst_day,
        }
    else:
        result["weekly"] = None
    
    if trend_30d:
        result["monthly"] = {
            "avg_sleep_hours": trend_30d.avg_sleep_hours,
            "trend": trend_30d.sleep_trend,
            "trend_percentage": trend_30d.trend_percentage,
            "consistency_score": trend_30d.consistency_score,
            "total_sessions": trend_30d.total_sessions,
        }
    else:
        result["monthly"] = None
    
    if include_ai_summary and (trend_7d or trend_30d):
        ai_insight = await analyzer.generate_ai_summary(
            baby_id=baby_id,
            trend_7d=trend_7d,
            trend_30d=trend_30d,
            baby_age_months=age_months,
            baby_name=baby.first_name
        )
        
        if ai_insight:
            result["ai_insights"] = {
                "summary": ai_insight.summary,
                "highlights": ai_insight.highlights,
                "concerns": ai_insight.concerns,
                "recommendations": ai_insight.recommendations,
                "age_comparison": ai_insight.age_comparison,
            }
        else:
            result["ai_insights"] = None
    
    return result
