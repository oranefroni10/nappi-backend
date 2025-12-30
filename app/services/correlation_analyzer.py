"""
Correlation Analyzer Service - Analyzes sensor data changes and generates insights.

This service is triggered after an awakening event to:
1. Fetch sensor data from the last hour before awakening
2. Calculate percentage changes for each sensor parameter
3. Filter parameters with significant changes (>=10% by default)
4. Generate AI insights using Gemini API
5. Store results in the Correlations table
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .babies_data import BabyDataManager
from ..core.settings import settings

logger = logging.getLogger(__name__)

# Sensor parameters to analyze
SENSOR_PARAMS = ["temp_celcius", "humidity", "noise_decibel", "heart_rate"]

# Lazy-loaded Gemini client
_gemini_client = None


def _get_gemini_client():
    """Lazy initialization of Gemini client."""
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


@dataclass
class ParameterChange:
    """Represents a change in a sensor parameter."""
    param_name: str
    start_value: float
    end_value: float
    change_percent: float
    direction: str  # "increase" or "decrease"


@dataclass
class CorrelationResult:
    """Result of correlation analysis."""
    baby_id: int
    correlation_id: Optional[int]
    parameters: Dict[str, Any]
    insights: Optional[str]
    success: bool
    error: Optional[str] = None


class CorrelationAnalyzer:
    """
    Analyzes sensor data changes around awakening events and generates
    AI-powered insights using Gemini API.
    """

    def __init__(self):
        self.baby_manager = BabyDataManager()
        self.change_threshold = settings.CORRELATION_CHANGE_THRESHOLD_PERCENT
        self.time_window_minutes = settings.CORRELATION_TIME_WINDOW_MINUTES

    async def analyze_awakening(
        self,
        baby_id: int,
        awakened_at: datetime,
        sleep_duration_minutes: float
    ) -> CorrelationResult:
        """
        Main method to analyze an awakening event.
        
        Args:
            baby_id: The ID of the baby who woke up
            awakened_at: Timestamp when the baby woke up
            sleep_duration_minutes: How long the baby slept
            
        Returns:
            CorrelationResult with analysis data and insights
        """
        logger.info(f"Starting correlation analysis for baby {baby_id}")

        try:
            # 1. Get sensor data from the time window before awakening
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

            # 2. Calculate parameter changes
            parameter_changes = self._calculate_parameter_changes(sensor_data)

            # 3. Filter significant changes (>=threshold)
            significant_changes = self._filter_significant_changes(parameter_changes)

            # 4. Build parameters dict for storage
            parameters_dict = self._build_parameters_dict(significant_changes)

            # 5. Generate AI insights using Gemini
            insights = await self._generate_gemini_insights(
                baby_id=baby_id,
                awakened_at=awakened_at,
                sleep_duration_minutes=sleep_duration_minutes,
                parameter_changes=significant_changes
            )

            # 6. Store in correlations table
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

    def _calculate_parameter_changes(
        self,
        sensor_data: List[Dict[str, Any]]
    ) -> List[ParameterChange]:
        """
        Calculate percentage changes for each sensor parameter.
        
        Compares the average of the first 25% of readings (start)
        with the average of the last 25% of readings (end).
        """
        if len(sensor_data) < 2:
            return []

        changes = []
        
        # Calculate window sizes (at least 1 reading each)
        quarter_size = max(1, len(sensor_data) // 4)
        start_readings = sensor_data[:quarter_size]
        end_readings = sensor_data[-quarter_size:]

        for param in SENSOR_PARAMS:
            # Get values for this parameter
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

            # Calculate averages
            start_avg = sum(start_values) / len(start_values)
            end_avg = sum(end_values) / len(end_values)

            # Avoid division by zero
            if start_avg == 0:
                if end_avg == 0:
                    continue
                change_percent = 100.0  # From 0 to something is 100% increase
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

    def _filter_significant_changes(
        self,
        changes: List[ParameterChange]
    ) -> List[ParameterChange]:
        """Filter to keep only changes above the threshold."""
        return [
            change for change in changes 
            if change.change_percent >= self.change_threshold
        ]

    def _build_parameters_dict(
        self,
        changes: List[ParameterChange]
    ) -> Dict[str, Any]:
        """Build the parameters dictionary for storage."""
        return {
            change.param_name: {
                "start_value": change.start_value,
                "end_value": change.end_value,
                "change_percent": change.change_percent,
                "direction": change.direction
            }
            for change in changes
        }

    async def _generate_gemini_insights(
        self,
        baby_id: int,
        awakened_at: datetime,
        sleep_duration_minutes: float,
        parameter_changes: List[ParameterChange]
    ) -> Optional[str]:
        """
        Generate AI insights about the awakening using Gemini API.
        Uses the official Google GenAI SDK with gemini-1.5-flash model.
        """
        client = _get_gemini_client()
        
        if not client:
            logger.warning("Gemini client not available, skipping insights")
            return None

        if not parameter_changes:
            return "No significant environmental changes detected before awakening."

        # Build prompt
        prompt = self._build_gemini_prompt(
            awakened_at=awakened_at,
            sleep_duration_minutes=sleep_duration_minutes,
            parameter_changes=parameter_changes
        )

        # Try multiple models in order of preference
        # Note: Model names change frequently - check https://ai.google.dev/gemini-api/docs/models
        models_to_try = [
            "gemini-2.0-flash-exp",      # Latest experimental
            "gemini-1.5-pro",            # Stable pro model
            "gemini-pro",                # Legacy stable model
        ]
        
        loop = asyncio.get_event_loop()
        
        for model_name in models_to_try:
            try:
                logger.debug(f"Trying model {model_name} for baby {baby_id}")
                response = await loop.run_in_executor(
                    None,
                    lambda m=model_name: client.models.generate_content(
                        model=m,
                        contents=prompt
                    )
                )
                
                if response and response.text:
                    logger.info(f"Generated Gemini insights for baby {baby_id} using {model_name}")
                    return response.text.strip()
                else:
                    logger.warning(f"Empty response from {model_name} for baby {baby_id}")
                    continue

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "quota" in error_str.lower() or "exhausted" in error_str.lower():
                    logger.warning(f"Rate limit on {model_name}, trying next model...")
                    continue
                elif "404" in error_str or "not found" in error_str.lower():
                    logger.debug(f"Model {model_name} not available, trying next...")
                    continue
                else:
                    logger.error(f"Error with {model_name}: {e}")
                    continue
        
        logger.warning(f"All Gemini models exhausted for baby {baby_id}")
        return None

    def _build_gemini_prompt(
        self,
        awakened_at: datetime,
        sleep_duration_minutes: float,
        parameter_changes: List[ParameterChange]
    ) -> str:
        """Build the prompt for Gemini API."""
        
        # Format time of day
        hour = awakened_at.hour
        if 5 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 17:
            time_of_day = "afternoon"
        elif 17 <= hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"

        # Format parameter changes
        changes_text = []
        for change in parameter_changes:
            param_display = {
                "temp_celcius": "Room temperature",
                "humidity": "Room humidity",
                "noise_decibel": "Noise level",
                "heart_rate": "Heart rate"
            }.get(change.param_name, change.param_name)
            
            changes_text.append(
                f"- {param_display}: {change.direction}d by {change.change_percent}% "
                f"(from {change.start_value} to {change.end_value})"
            )

        changes_formatted = "\n".join(changes_text)

        prompt = f"""You are a pediatric sleep consultant AI. Analyze the following baby sleep data and provide brief, actionable insights about what may have caused the baby to wake up.

Context:
- Time of awakening: {time_of_day} ({awakened_at.strftime('%H:%M')})
- Sleep duration before waking: {sleep_duration_minutes:.0f} minutes

Environmental changes detected in the hour before awakening:
{changes_formatted}

Provide a concise analysis (2-3 sentences) explaining:
1. Which environmental factor(s) most likely contributed to the awakening
2. One practical suggestion for parents to improve sleep conditions

Keep the response friendly and helpful. Focus on actionable advice."""

        return prompt


# Convenience function for direct use
async def analyze_awakening(
    baby_id: int,
    awakened_at: datetime,
    sleep_duration_minutes: float
) -> CorrelationResult:
    """
    Analyze an awakening event and generate insights.
    
    This is a convenience function that creates a CorrelationAnalyzer
    and runs the analysis.
    """
    analyzer = CorrelationAnalyzer()
    return await analyzer.analyze_awakening(
        baby_id=baby_id,
        awakened_at=awakened_at,
        sleep_duration_minutes=sleep_duration_minutes
    )
