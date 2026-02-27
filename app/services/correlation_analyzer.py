"""Analyzes sensor changes around awakenings and generates AI insights."""

import logging
import asyncio
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .babies_data import BabyDataManager
from ..core.settings import settings
from ..core.constants import (
    HEALTHY_RANGES, CORRELATION_MAX_NOTES_CHARS, DAYS_PER_MONTH,
    GEMINI_INSIGHTS_TEMPERATURE, GEMINI_INSIGHTS_MAX_TOKENS, GEMINI_INSIGHTS_TOP_P,
    GEMINI_QUICK_INSIGHT_TEMPERATURE, GEMINI_QUICK_INSIGHT_MAX_TOKENS,
    AI_MORNING_START, AI_MORNING_END, AI_AFTERNOON_END, AI_EVENING_END,
    CORRELATION_QUARTILE_FRACTION,
    TEMP_OPTIMAL_HIGH_C, TEMP_OPTIMAL_LOW_C,
    NOISE_ALERT_HIGH_DB, HUMIDITY_OPTIMAL_HIGH_PCT, HUMIDITY_OPTIMAL_LOW_PCT,
)
from ..utils.sleep_blocks import group_into_sleep_blocks

logger = logging.getLogger(__name__)

SENSOR_PARAMS = ["temp_celcius", "humidity", "noise_decibel"]

_gemini_client = None


# Used by: CorrelationAnalyzer._generate_gemini_insights(), _generate_enhanced_insights(), generate_quick_insight()
def _get_gemini_client():
    """Lazy init of Gemini client."""
    global _gemini_client
    if _gemini_client is None and settings.GEMINI_API_KEY:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            logger.info("Gemini client initialized successfully")
        except ImportError:
            logger.warning("google-genai package not installed, Gemini insights disabled")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
    return _gemini_client


SYSTEM_INSTRUCTION = """You are a warm, knowledgeable pediatric sleep consultant helping parents understand their baby's sleep patterns.

Your role:
- Analyze sensor data and environmental factors that may affect baby sleep
- Provide evidence-based, practical suggestions (not orders)
- Be reassuring and supportive, never alarming or dramatic
- Keep responses concise (3-4 sentences max)
- Prioritize gentle, actionable tips parents can try tonight

Tone guidelines:
- Use soft language like "we noticed", "you might want to", "it could help to", "it looks like"
- Avoid dramatic words like "significant", "critical", "alarming", "drastic", "severe"
- Frame suggestions as options, not commands (e.g., "you could try..." instead of "do this")
- Downplay minor changes — small environmental shifts are normal and don't need dramatic framing

Remember:
- Baby sleep is highly variable and often unpredictable
- Many awakenings are normal and age-appropriate
- Environmental factors are just one piece of the puzzle
- When no clear cause is found, normalize the experience for parents"""


@dataclass
class ParameterChange:
    param_name: str
    start_value: float
    end_value: float
    change_percent: float
    direction: str  # "increase" or "decrease"


@dataclass
class CorrelationResult:
    baby_id: int
    correlation_id: Optional[int]
    parameters: Dict[str, Any]
    insights: Optional[str]
    success: bool
    error: Optional[str] = None


@dataclass
class StructuredInsight:
    likely_cause: str
    actionable_tips: List[str]
    environment_assessment: str
    age_context: str
    sleep_quality_note: str  # AI-generated per-awakening note
    raw_text: str


@dataclass
class EnhancedCorrelationResult:
    baby_id: int
    correlation_id: Optional[int]
    parameters: Dict[str, Any]
    insights: Optional[StructuredInsight]
    simple_insight: Optional[str]
    success: bool
    error: Optional[str] = None


@dataclass
class BabyContext:
    name: str
    age_months: int
    optimal_temp: Optional[float]
    optimal_humidity: Optional[float]
    optimal_noise: Optional[float]
    recent_awakenings_24h: int
    last_sensor_values: Dict[str, float]
    notes: Optional[str] = None


class CorrelationAnalyzer:

    def __init__(self):
        self.baby_manager = BabyDataManager()
        self.change_thresholds = settings.CORRELATION_CHANGE_THRESHOLDS
        self.time_window_minutes = settings.CORRELATION_TIME_WINDOW_MINUTES

    # Used by: self.analyze_awakening(), self.analyze_awakening_enhanced()
    async def _get_baby_context(
        self,
        baby_id: int,
        awakened_at: datetime,
        sensor_data: List[Dict[str, Any]]
    ) -> Optional[BabyContext]:
        """Fetch baby context for AI insights."""
        try:
            babies = await self.baby_manager.get_babies_list()
            baby = next((b for b in babies if b.id == baby_id), None)

            if not baby:
                return None

            today = awakened_at.date()
            age_days = (today - baby.birthdate).days
            age_months = age_days // DAYS_PER_MONTH
            optimal_stats = await self._get_optimal_stats(baby_id)
            recent_awakenings = await self._count_recent_awakenings(baby_id, awakened_at)

            last_values = {}
            if sensor_data:
                last_reading = sensor_data[-1]
                for param in SENSOR_PARAMS:
                    if last_reading.get(param) is not None:
                        last_values[param] = last_reading[param]

            notes = await self.baby_manager.get_baby_notes(baby_id)
            truncated_notes = notes if notes else None  # List[BabyNote]; max notes count is negligible in practice

            return BabyContext(
                name=baby.first_name,
                age_months=age_months,
                optimal_temp=optimal_stats.get("temperature"),
                optimal_humidity=optimal_stats.get("humidity"),
                optimal_noise=optimal_stats.get("noise"),
                recent_awakenings_24h=recent_awakenings,
                last_sensor_values=last_values,
                notes=truncated_notes
            )
        except Exception as e:
            logger.warning(f"Failed to get baby context: {e}")
            return None

    # Used by: self._get_baby_context()
    async def _get_optimal_stats(self, baby_id: int) -> Dict[str, Optional[float]]:
        """Get optimal conditions from optimal_stats table."""
        try:
            from sqlalchemy import text
            async with self.baby_manager.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT temperature, humidity, noise
                        FROM "Nappi"."optimal_stats"
                        WHERE baby_id = :baby_id
                    '''),
                    {"baby_id": baby_id}
                )
                row = result.mappings().first()
                if row:
                    return dict(row)
        except Exception as e:
            logger.warning(f"Failed to get optimal stats: {e}")
        return {}

    # Used by: self._get_baby_context()
    async def _count_recent_awakenings(
        self,
        baby_id: int,
        awakened_at: datetime
    ) -> int:
        """Count sleep blocks (not raw events) in last 24h."""
        try:
            start_time = awakened_at - timedelta(hours=24)
            events = await self.baby_manager.get_awakening_events_for_period(
                baby_id=baby_id,
                start_time=start_time,
                end_time=awakened_at
            )
            if not events:
                return 0
            blocks = group_into_sleep_blocks(
                events, source="events_for_period"
            )
            return len(blocks)
        except Exception as e:
            logger.warning(f"Failed to count recent awakenings: {e}")
            return 0

    # Used by: stats.py, analyze_awakening()
    async def analyze_awakening(
        self,
        baby_id: int,
        awakened_at: datetime,
        sleep_duration_minutes: float
    ) -> CorrelationResult:
        """Main analysis entry point."""
        logger.info(f"Starting correlation analysis for baby {baby_id}")

        try:
            start_time = awakened_at - timedelta(minutes=self.time_window_minutes)
            sensor_data = await self.baby_manager.get_sensor_data_range(
                baby_id=baby_id,
                start_time=start_time,
                end_time=awakened_at
            )

            if not sensor_data or len(sensor_data) < 2:
                logger.warning(
                    f"Insufficient sensor data for baby {baby_id} "
                    f"(found {len(sensor_data) if sensor_data else 0} records)"
                )
                return CorrelationResult(
                    baby_id=baby_id,
                    correlation_id=None,
                    parameters={},
                    insights=None,
                    success=False,
                    error="Insufficient sensor data for analysis"
                )

            parameter_changes = self._calculate_parameter_changes(sensor_data)
            significant_changes = self._filter_significant_changes(parameter_changes)
            parameters_dict = self._build_parameters_dict(significant_changes)
            baby_context = await self._get_baby_context(baby_id, awakened_at, sensor_data)
            insights = await self._generate_gemini_insights(
                baby_id=baby_id,
                awakened_at=awakened_at,
                sleep_duration_minutes=sleep_duration_minutes,
                parameter_changes=significant_changes,
                baby_context=baby_context
            )
            correlation_id = await self.baby_manager.insert_correlation(
                baby_id=baby_id,
                correlation_time=awakened_at,
                parameters=parameters_dict,
                extra_data=insights
            )

            logger.info(
                f"Correlation analysis complete for baby {baby_id}: "
                f"{len(significant_changes)} significant changes found"
            )

            return CorrelationResult(
                baby_id=baby_id,
                correlation_id=correlation_id,
                parameters=parameters_dict,
                insights=insights,
                success=True
            )

        except Exception as e:
            logger.error(
                f"Error in correlation analysis for baby {baby_id}: {e}",
                exc_info=True
            )
            return CorrelationResult(
                baby_id=baby_id,
                correlation_id=None,
                parameters={},
                insights=None,
                success=False,
                error=str(e)
            )

    # Used by: self.analyze_awakening(), self.analyze_awakening_enhanced()
    def _calculate_parameter_changes(
        self,
        sensor_data: List[Dict[str, Any]]
    ) -> List[ParameterChange]:
        """Compare first vs last 25% of readings."""
        if len(sensor_data) < 2:
            return []

        changes = []
        quarter_size = max(1, int(len(sensor_data) * CORRELATION_QUARTILE_FRACTION))
        start_readings = sensor_data[:quarter_size]
        end_readings = sensor_data[-quarter_size:]

        for param in SENSOR_PARAMS:
            start_values = [
                r[param] for r in start_readings
                if r.get(param) is not None
            ]
            end_values = [
                r[param] for r in end_readings
                if r.get(param) is not None
            ]

            if not start_values or not end_values:
                continue

            start_avg = sum(start_values) / len(start_values)
            end_avg = sum(end_values) / len(end_values)

            if start_avg == 0:
                if end_avg == 0:
                    continue
                change_percent = 100.0
            else:
                change_percent = abs((end_avg - start_avg) / start_avg) * 100

            direction = "increase" if end_avg > start_avg else "decrease"

            changes.append(ParameterChange(
                param_name=param,
                start_value=round(start_avg, 2),
                end_value=round(end_avg, 2),
                change_percent=round(change_percent, 2),
                direction=direction
            ))

        return changes

    # Used by: self.analyze_awakening(), self.analyze_awakening_enhanced()
    def _filter_significant_changes(
        self,
        changes: List[ParameterChange]
    ) -> List[ParameterChange]:
        """Keep only changes above per-parameter threshold."""
        return [
            change for change in changes
            if change.change_percent >= self.change_thresholds.get(change.param_name, 10.0)
        ]

    # Used by: self.analyze_awakening(), self.analyze_awakening_enhanced()
    def _build_parameters_dict(
        self,
        changes: List[ParameterChange]
    ) -> Dict[str, Any]:
        return {
            change.param_name: {
                "start_value": change.start_value,
                "end_value": change.end_value,
                "change_percent": change.change_percent,
                "direction": change.direction
            }
            for change in changes
        }

    # Used by: self.analyze_awakening()
    async def _generate_gemini_insights(
        self,
        baby_id: int,
        awakened_at: datetime,
        sleep_duration_minutes: float,
        parameter_changes: List[ParameterChange],
        baby_context: Optional[BabyContext]
    ) -> Optional[str]:
        """Generate AI insights via Gemini."""
        client = _get_gemini_client()

        if not client:
            logger.warning("Gemini client not available, skipping insights")
            return None

        prompt = self._build_gemini_prompt(
            awakened_at=awakened_at,
            sleep_duration_minutes=sleep_duration_minutes,
            significant_changes=parameter_changes,
            baby_context=baby_context
        )
        model_name = settings.GEMINI_MODEL_INSIGHTS

        from google.genai import types
        generation_config = types.GenerateContentConfig(
            temperature=GEMINI_INSIGHTS_TEMPERATURE,
            max_output_tokens=GEMINI_INSIGHTS_MAX_TOKENS,
            top_p=GEMINI_INSIGHTS_TOP_P,
        )
        loop = asyncio.get_event_loop()

        try:
            logger.debug(f"Calling Gemini ({model_name}) for baby {baby_id}")

            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=generation_config,
                )
            )

            if response and response.text:
                text = response.text.strip()
                # Check for potentially incomplete response
                if text and text[-1] not in '.!?:)"\'':
                    logger.warning(f"Potentially incomplete insight response for baby {baby_id} - may have been truncated")
                logger.info(f"Generated Gemini insights for baby {baby_id}")
                return text
            else:
                logger.warning(f"Empty response from Gemini for baby {baby_id}")
                return None

        except Exception as e:
            logger.error(f"Gemini API error for baby {baby_id}: {e}")
            return None

    # Used by: self._generate_gemini_insights()
    def _build_gemini_prompt(
        self,
        awakened_at: datetime,
        sleep_duration_minutes: float,
        significant_changes: List[ParameterChange],
        baby_context: Optional[BabyContext]
    ) -> str:
        """Build enriched prompt for Gemini."""
        hour = awakened_at.hour
        if AI_MORNING_START <= hour < AI_MORNING_END:
            time_of_day = "morning"
        elif AI_MORNING_END <= hour < AI_AFTERNOON_END:
            time_of_day = "afternoon"
        elif AI_AFTERNOON_END <= hour < AI_EVENING_END:
            time_of_day = "evening"
        else:
            time_of_day = "night"

        baby_info = ""
        if baby_context:
            age_str = self._format_age(baby_context.age_months)
            notes_text = f"\n- Parent Notes: {baby_context.notes}" if baby_context.notes else ""
            baby_info = f"""
Baby Information:
- Name: {baby_context.name}
- Age: {age_str}
- Awakenings in last 24 hours: {baby_context.recent_awakenings_24h} (including this one){notes_text}
"""

        current_values_text = ""
        if baby_context and baby_context.last_sensor_values:
            values_lines = []
            for param, value in baby_context.last_sensor_values.items():
                info = HEALTHY_RANGES.get(param, {})
                name = info.get("name", param)
                unit = info.get("unit", "")
                min_val = info.get("min", 0)
                max_val = info.get("max", 100)

                status = "normal"
                if value < min_val:
                    status = "below recommended"
                elif value > max_val:
                    status = "above recommended"

                values_lines.append(f"- {name}: {value}{unit} ({status}, healthy range: {min_val}-{max_val}{unit})")

            current_values_text = "\nCurrent Room Conditions (at time of awakening):\n" + "\n".join(values_lines)

        optimal_comparison = ""
        if baby_context:
            comparisons = []
            if baby_context.optimal_temp and baby_context.last_sensor_values.get("temp_celcius"):
                current_temp = baby_context.last_sensor_values["temp_celcius"]
                diff = current_temp - baby_context.optimal_temp
                if abs(diff) > 1:
                    direction = "warmer" if diff > 0 else "cooler"
                    comparisons.append(f"- Temperature is {abs(diff):.1f}°C {direction} than this baby's optimal ({baby_context.optimal_temp}°C)")

            if baby_context.optimal_humidity and baby_context.last_sensor_values.get("humidity"):
                current_hum = baby_context.last_sensor_values["humidity"]
                diff = current_hum - baby_context.optimal_humidity
                if abs(diff) > 5:
                    direction = "higher" if diff > 0 else "lower"
                    comparisons.append(f"- Humidity is {abs(diff):.0f}% {direction} than optimal ({baby_context.optimal_humidity}%)")

            if baby_context.optimal_noise and baby_context.last_sensor_values.get("noise_decibel"):
                current_noise = baby_context.last_sensor_values["noise_decibel"]
                diff = current_noise - baby_context.optimal_noise
                if abs(diff) > 5:
                    direction = "louder" if diff > 0 else "quieter"
                    comparisons.append(f"- Noise is {abs(diff):.0f}dB {direction} than optimal ({baby_context.optimal_noise}dB)")

            if comparisons:
                optimal_comparison = "\nComparison to Baby's Historical Optimal Conditions:\n" + "\n".join(comparisons)

        changes_text = ""
        if significant_changes:
            changes_lines = []
            for change in significant_changes:
                info = HEALTHY_RANGES.get(change.param_name, {})
                name = info.get("name", change.param_name)
                unit = info.get("unit", "")

                changes_lines.append(
                    f"- {name}: {change.direction}d by {change.change_percent:.0f}% "
                    f"(from {change.start_value}{unit} to {change.end_value}{unit})"
                )
            changes_text = "\nEnvironmental Changes We Noticed (in the hour before awakening):\n" + "\n".join(changes_lines)
        else:
            changes_text = "\nEnvironmental Changes: Nothing notable detected (within normal variation)"

        sleep_hours = sleep_duration_minutes / 60
        # Sadeh et al., J Sleep Res 2009;18:60-73, p.63 Table 2:
        # 0-2m nighttime 8.50±1.83h; 3-5m 9.47h; 6-8m 9.86h; 9-11m 9.92h; 12-17m 10.3h
        if baby_context:
            age_months = baby_context.age_months
            if age_months < 4:
                expected_night = "8-9 hours"
                expected_nap = "30min-2 hours"
            elif age_months < 12:
                expected_night = "9-11 hours"
                expected_nap = "1-2 hours"
            else:
                expected_night = "10-12 hours"
                expected_nap = "1-3 hours"

            if time_of_day in ["morning", "afternoon"]:
                sleep_context = f"(typical nap duration for this age: {expected_nap})"
            else:
                sleep_context = f"(typical night sleep stretch for this age: {expected_night})"
        else:
            sleep_context = ""

        prompt = f"""{SYSTEM_INSTRUCTION}

---

=== AWAKENING EVENT ===
- Time: {awakened_at.strftime('%H:%M')} ({time_of_day})
- Sleep duration before waking: {sleep_hours:.1f} hours ({sleep_duration_minutes:.0f} minutes) {sleep_context}
{baby_info}{current_values_text}{optimal_comparison}{changes_text}

=== HEALTHY REFERENCE RANGES ===
- Room temperature: {TEMP_OPTIMAL_LOW_C}-{TEMP_OPTIMAL_HIGH_C}°C (babies sleep best in slightly cool rooms)
- Humidity: 40-60% (comfort range; EPA ideal is 30-50%)
- Noise: under 50dB (quiet environment, though white noise up to 50dB can help)

=== YOUR TASK ===
Provide a brief, helpful analysis (3-4 sentences) that:

1. **Identifies the most likely cause** of this awakening based on the data above
2. **Gives one specific, actionable tip** the parents can try tonight
3. **Reassures or contextualizes** if the awakening seems normal for the baby's age

Guidelines:
- Be warm and supportive, never dramatic or alarming
- Use gentle language: "we noticed", "you might want to try", "it could help" — not commands
- Avoid words like "significant", "critical", "drastic" — keep it calm and matter-of-fact
- If no notable changes detected, consider other factors (age-appropriate wake patterns, hunger, developmental leaps)
- Prioritize the most relevant factor if multiple issues exist
- Keep advice practical and framed as suggestions

Respond in a conversational tone as if chatting with a friend who happens to be a parent."""

        return prompt

    # Used by: self._generate_enhanced_insights()
    def _build_enhanced_prompt(
        self,
        awakened_at: datetime,
        sleep_duration_minutes: float,
        significant_changes: List[ParameterChange],
        baby_context: Optional[BabyContext]
    ) -> str:
        """Build prompt for structured multi-section response."""
        hour = awakened_at.hour
        if AI_MORNING_START <= hour < AI_MORNING_END:
            time_of_day = "morning"
        elif AI_MORNING_END <= hour < AI_AFTERNOON_END:
            time_of_day = "afternoon"
        elif AI_AFTERNOON_END <= hour < AI_EVENING_END:
            time_of_day = "evening"
        else:
            time_of_day = "night"

        baby_info = ""
        baby_name = "Baby"
        if baby_context:
            baby_name = baby_context.name
            age_str = self._format_age(baby_context.age_months)
            notes_text = f"\n- Parent Notes: {baby_context.notes}" if baby_context.notes else ""
            baby_info = f"""
Baby Information:
- Name: {baby_context.name}
- Age: {age_str}
- Awakenings in last 24 hours: {baby_context.recent_awakenings_24h} (including this one){notes_text}
"""

        current_values_text = ""
        if baby_context and baby_context.last_sensor_values:
            values_lines = []
            for param, value in baby_context.last_sensor_values.items():
                info = HEALTHY_RANGES.get(param, {})
                name = info.get("name", param)
                unit = info.get("unit", "")
                min_val = info.get("min", 0)
                max_val = info.get("max", 100)

                status = "normal"
                if value < min_val:
                    status = "below recommended"
                elif value > max_val:
                    status = "above recommended"

                values_lines.append(f"- {name}: {value}{unit} ({status}, healthy range: {min_val}-{max_val}{unit})")

            current_values_text = "\nCurrent Room Conditions:\n" + "\n".join(values_lines)

        changes_text = ""
        if significant_changes:
            changes_lines = []
            for change in significant_changes:
                info = HEALTHY_RANGES.get(change.param_name, {})
                name = info.get("name", change.param_name)
                unit = info.get("unit", "")

                changes_lines.append(
                    f"- {name}: {change.direction}d by {change.change_percent:.0f}% "
                    f"(from {change.start_value}{unit} to {change.end_value}{unit})"
                )
            changes_text = "\nEnvironmental Changes We Noticed:\n" + "\n".join(changes_lines)
        else:
            changes_text = "\nEnvironmental Changes: Nothing notable detected"

        sleep_hours = sleep_duration_minutes / 60

        prompt = f"""You are a pediatric sleep consultant analyzing {baby_name}'s sleep data.
{baby_info}{current_values_text}{changes_text}

Awakening Time: {awakened_at.strftime('%H:%M')} ({time_of_day})
Sleep Duration: {sleep_hours:.1f} hours ({sleep_duration_minutes:.0f} minutes)

Provide your analysis in this EXACT format with these sections:

LIKELY_CAUSE: (1-2 sentences explaining the most probable reason for this awakening)

TIPS:
- (First actionable tip parents can try)
- (Second actionable tip)
- (Third actionable tip if relevant, otherwise omit)

ENVIRONMENT: (1 sentence assessment of current room conditions - are they optimal or need adjustment?)

AGE_CONTEXT: (1 sentence about how this sleep pattern relates to typical babies this age)

SLEEP_QUALITY: (1 sentence about the quality/duration of this sleep session — this is an AI-generated note per awakening, not the removed sleep_quality_score metric)

Be warm, practical, and reassuring. Frame tips as gentle suggestions, not orders. Avoid dramatic language — keep observations calm and matter-of-fact."""

        return prompt

    # Used by: self._generate_enhanced_insights()
    def _parse_structured_insight(self, response_text: str) -> StructuredInsight:
        """Parse AI response into structured sections."""
        likely_cause = ""
        actionable_tips = []
        environment_assessment = ""
        age_context = ""
        sleep_quality_note = ""

        current_section = None

        for line in response_text.split('\n'):
            line = line.strip()

            if line.startswith("LIKELY_CAUSE:"):
                current_section = "cause"
                likely_cause = line.replace("LIKELY_CAUSE:", "").strip()
            elif line.startswith("TIPS:"):
                current_section = "tips"
            elif line.startswith("ENVIRONMENT:"):
                current_section = "environment"
                environment_assessment = line.replace("ENVIRONMENT:", "").strip()
            elif line.startswith("AGE_CONTEXT:"):
                current_section = "age"
                age_context = line.replace("AGE_CONTEXT:", "").strip()
            elif line.startswith("SLEEP_QUALITY:"):
                current_section = "quality"
                sleep_quality_note = line.replace("SLEEP_QUALITY:", "").strip()
            elif line.startswith("- ") and current_section == "tips":
                actionable_tips.append(line[2:].strip())
            elif line and current_section == "cause" and not line.startswith("-"):
                likely_cause += " " + line
            elif line and current_section == "environment" and not line.startswith("-"):
                environment_assessment += " " + line
            elif line and current_section == "age" and not line.startswith("-"):
                age_context += " " + line
            elif line and current_section == "quality" and not line.startswith("-"):
                sleep_quality_note += " " + line

        # Fallbacks if parsing didn't work well
        if not likely_cause:
            likely_cause = "Unable to determine specific cause from available data."
        if not actionable_tips:
            actionable_tips = ["Continue monitoring sleep patterns for more insights."]
        if not environment_assessment:
            environment_assessment = "Room conditions are being monitored."
        if not age_context:
            age_context = "Sleep patterns vary significantly at this age."
        if not sleep_quality_note:
            sleep_quality_note = "Sleep duration is being tracked."

        return StructuredInsight(
            likely_cause=likely_cause.strip(),
            actionable_tips=actionable_tips[:3],
            environment_assessment=environment_assessment.strip(),
            age_context=age_context.strip(),
            sleep_quality_note=sleep_quality_note.strip(),
            raw_text=response_text
        )

    # Used by: stats.py
    async def analyze_awakening_enhanced(
        self,
        baby_id: int,
        awakened_at: datetime,
        sleep_duration_minutes: float
    ) -> EnhancedCorrelationResult:
        """Enhanced analysis with structured insights."""
        logger.info(f"Starting enhanced correlation analysis for baby {baby_id}")

        try:
            start_time = awakened_at - timedelta(minutes=self.time_window_minutes)
            sensor_data = await self.baby_manager.get_sensor_data_range(
                baby_id=baby_id,
                start_time=start_time,
                end_time=awakened_at
            )

            if not sensor_data or len(sensor_data) < 2:
                logger.warning(f"Insufficient sensor data for baby {baby_id}")
                return EnhancedCorrelationResult(
                    baby_id=baby_id,
                    correlation_id=None,
                    parameters={},
                    insights=None,
                    simple_insight=None,
                    success=False,
                    error="Insufficient sensor data for analysis"
                )

            parameter_changes = self._calculate_parameter_changes(sensor_data)
            significant_changes = self._filter_significant_changes(parameter_changes)
            parameters_dict = self._build_parameters_dict(significant_changes)
            baby_context = await self._get_baby_context(baby_id, awakened_at, sensor_data)
            structured_insight = await self._generate_enhanced_insights(
                baby_id=baby_id,
                awakened_at=awakened_at,
                sleep_duration_minutes=sleep_duration_minutes,
                parameter_changes=significant_changes,
                baby_context=baby_context
            )
            simple_insight = await generate_quick_insight(
                baby_id=baby_id,
                awakened_at=awakened_at,
                sleep_duration_minutes=sleep_duration_minutes,
                last_sensor_readings=baby_context.last_sensor_values if baby_context else None
            )
            insights_text = structured_insight.raw_text if structured_insight else None
            correlation_id = await self.baby_manager.insert_correlation(
                baby_id=baby_id,
                correlation_time=awakened_at,
                parameters=parameters_dict,
                extra_data=insights_text
            )

            logger.info(f"Enhanced analysis complete for baby {baby_id}")

            return EnhancedCorrelationResult(
                baby_id=baby_id,
                correlation_id=correlation_id,
                parameters=parameters_dict,
                insights=structured_insight,
                simple_insight=simple_insight,
                success=True
            )

        except Exception as e:
            logger.error(f"Error in enhanced analysis for baby {baby_id}: {e}", exc_info=True)
            return EnhancedCorrelationResult(
                baby_id=baby_id,
                correlation_id=None,
                parameters={},
                insights=None,
                simple_insight=None,
                success=False,
                error=str(e)
            )

    # Used by: self.analyze_awakening_enhanced()
    async def _generate_enhanced_insights(
        self,
        baby_id: int,
        awakened_at: datetime,
        sleep_duration_minutes: float,
        parameter_changes: List[ParameterChange],
        baby_context: Optional[BabyContext]
    ) -> Optional[StructuredInsight]:
        """Generate structured multi-section AI insights."""
        client = _get_gemini_client()

        if not client:
            logger.warning("Gemini client not available")
            return None

        prompt = self._build_enhanced_prompt(
            awakened_at=awakened_at,
            sleep_duration_minutes=sleep_duration_minutes,
            significant_changes=parameter_changes,
            baby_context=baby_context
        )

        try:
            from google.genai import types

            loop = asyncio.get_event_loop()
            model_name = settings.GEMINI_MODEL_INSIGHTS
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=GEMINI_INSIGHTS_TEMPERATURE,
                        max_output_tokens=GEMINI_INSIGHTS_MAX_TOKENS,
                    ),
                )
            )

            if response and response.text:
                text = response.text.strip()
                # Check for potentially incomplete response
                if text and text[-1] not in '.!?:)"\'':
                    logger.warning(f"Potentially incomplete enhanced insight for baby {baby_id} - may have been truncated")
                logger.info(f"Generated enhanced insights for baby {baby_id}")
                return self._parse_structured_insight(text)

        except Exception as e:
            logger.error(f"Enhanced insight generation failed for baby {baby_id}: {e}")

        return None

    # Used by: self._build_gemini_prompt(), self._build_enhanced_prompt()
    def _format_age(self, age_months: int) -> str:
        """Format age for AI prompts."""
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


# Used by: convenience wrapper (callers use CorrelationAnalyzer directly)
async def analyze_awakening(
    baby_id: int,
    awakened_at: datetime,
    sleep_duration_minutes: float
) -> CorrelationResult:
    """Convenience wrapper around CorrelationAnalyzer."""
    analyzer = CorrelationAnalyzer()
    return await analyzer.analyze_awakening(
        baby_id=baby_id,
        awakened_at=awakened_at,
        sleep_duration_minutes=sleep_duration_minutes
    )


# Used by: sensor_events.py, analyze_awakening_enhanced()
async def generate_quick_insight(
    baby_id: int,
    awakened_at: datetime,
    sleep_duration_minutes: float,
    last_sensor_readings: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Quick 1-2 sentence insight for sleep-end."""
    client = _get_gemini_client()

    if not client:
        logger.warning("Gemini client not available for quick insight")
        return None

    hour = awakened_at.hour
    if AI_MORNING_START <= hour < AI_MORNING_END:
        time_of_day = "morning"
    elif AI_MORNING_END <= hour < AI_AFTERNOON_END:
        time_of_day = "afternoon"
    elif AI_AFTERNOON_END <= hour < AI_EVENING_END:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    sleep_hours = sleep_duration_minutes / 60
    sensor_info = ""
    if last_sensor_readings:
        parts = []
        if last_sensor_readings.get("temp_celcius"):
            temp = last_sensor_readings["temp_celcius"]
            status = "warm" if temp > TEMP_OPTIMAL_HIGH_C else ("cool" if temp < TEMP_OPTIMAL_LOW_C else "normal")
            parts.append(f"room {status} ({temp}°C)")
        if last_sensor_readings.get("noise_decibel"):
            noise = last_sensor_readings["noise_decibel"]
            status = "noisy" if noise > NOISE_ALERT_HIGH_DB else "quiet"
            parts.append(f"{status} ({noise}dB)")
        if last_sensor_readings.get("humidity"):
            hum = last_sensor_readings["humidity"]
            status = "humid" if hum > HUMIDITY_OPTIMAL_HIGH_PCT else ("dry" if hum < HUMIDITY_OPTIMAL_LOW_PCT else "normal humidity")
            parts.append(f"{status} ({hum}%)")
        if parts:
            sensor_info = f"Room conditions: {', '.join(parts)}."

    prompt = f"""Baby woke up at {awakened_at.strftime('%H:%M')} ({time_of_day}) after sleeping {sleep_hours:.1f} hours.
{sensor_info}

In exactly 1-2 short sentences, explain the most likely reason for waking and one gentle suggestion. Be warm, concise, and avoid dramatic language."""

    try:
        from google.genai import types

        loop = asyncio.get_event_loop()
        model_name = settings.GEMINI_MODEL_INSIGHTS
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=GEMINI_QUICK_INSIGHT_TEMPERATURE,
                    max_output_tokens=GEMINI_QUICK_INSIGHT_MAX_TOKENS,
                ),
            )
        )

        if response and response.text:
            text = response.text.strip()
            # Check for potentially incomplete response
            if text and text[-1] not in '.!?:)"\'':
                logger.warning(f"Potentially incomplete quick insight for baby {baby_id} - may have been truncated")
            logger.info(f"Generated quick insight for baby {baby_id}")
            return text

    except Exception as e:
        logger.error(f"Quick insight generation failed for baby {baby_id}: {e}")

    return None
