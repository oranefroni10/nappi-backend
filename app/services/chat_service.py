"""
Chat Service - AI-powered chat with full baby context.

This service provides conversational AI capabilities with comprehensive
baby context including:
- Baby profile and parent notes
- Optimal sleep conditions
- Recent awakenings with AI insights
- Correlation analysis (awakening causes)
- Sleep patterns
- Daily summaries
- Current room conditions
"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional

from .babies_data import BabyDataManager
from .sleep_patterns import analyze_sleep_patterns
from ..core.settings import settings

logger = logging.getLogger(__name__)

# Token size limits to prevent prompt blow-ups
MAX_NOTES_CHARS = 1000
MAX_CHAT_HISTORY = 10
MAX_AWAKENINGS = 5
MAX_CORRELATIONS = 5
MAX_SUMMARY_DAYS = 7

# Lazy-loaded Gemini client (shared with correlation_analyzer)
_gemini_client = None


def _get_gemini_client():
    """Lazy initialization of Gemini client."""
    global _gemini_client
    if _gemini_client is None and settings.GEMINI_API_KEY:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            logger.info("Gemini client initialized for chat service")
        except ImportError:
            logger.warning("google-genai package not installed, chat disabled")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
    return _gemini_client


class ChatService:
    """
    AI-powered chat service with full baby context.
    
    Provides rich, personalized responses based on all available baby data.
    """
    
    def __init__(self):
        self.baby_manager = BabyDataManager()
    
    async def get_full_baby_context(self, baby_id: int) -> Dict[str, Any]:
        """
        Fetch ALL available context for rich, insightful chat responses.
        
        Args:
            baby_id: The ID of the baby
            
        Returns:
            Dictionary containing all baby context data
        """
        # Baby info + notes (formatted from multi-note system)
        baby = await self.baby_manager.get_baby_by_id(baby_id)
        notes = await self.baby_manager.get_baby_notes_formatted(baby_id)
        
        # Optimal stats (learned ideal conditions)
        optimal = await self.baby_manager.get_optimal_stats(baby_id)
        
        # Recent awakenings with AI insights
        awakenings = await self.baby_manager.get_recent_awakenings_with_insights(
            baby_id, limit=MAX_AWAKENINGS
        )
        
        # Correlations (what caused each awakening - sensor changes analysis)
        correlations = await self.baby_manager.get_recent_correlations(
            baby_id, limit=MAX_CORRELATIONS
        )
        
        # Last 7 days daily summaries (averages, awakening counts)
        summaries = await self.baby_manager.get_daily_summaries_range(
            baby_id,
            start_date=date.today() - timedelta(days=MAX_SUMMARY_DAYS),
            end_date=date.today()
        )
        
        # Sleep patterns for current month (clustered nap/night times)
        now = datetime.now()
        raw_sessions = await self.baby_manager.get_sleep_sessions_for_month(
            baby_id, year=now.year, month=now.month
        )
        sleep_patterns = analyze_sleep_patterns(raw_sessions) if raw_sessions else []
        
        # Current room conditions (latest sensor reading)
        current_room = await self.baby_manager.get_last_sensor_readings(baby_id)
        
        return {
            "baby": baby,
            "notes": notes[:MAX_NOTES_CHARS] if notes else None,  # Truncate combined notes if too long
            "optimal_stats": optimal or {},
            "recent_awakenings": awakenings,
            "correlations": correlations,
            "daily_summaries": summaries,
            "sleep_patterns": sleep_patterns,
            "current_room": current_room,
        }
    
    def _format_age(self, baby) -> str:
        """Format baby's age in a readable way."""
        if not baby or not baby.birthdate:
            return "unknown age"
        
        today = date.today()
        age_days = (today - baby.birthdate).days
        age_months = age_days // 30
        
        if age_months < 1:
            return f"{age_days} days old"
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
    
    def _format_room(self, room_data: Optional[Dict]) -> str:
        """Format current room conditions."""
        if not room_data:
            return "No current room data available"
        
        parts = []
        if room_data.get("temp_celcius"):
            parts.append(f"Temperature: {room_data['temp_celcius']:.1f}°C")
        if room_data.get("humidity"):
            parts.append(f"Humidity: {room_data['humidity']:.0f}%")
        if room_data.get("noise_decibel"):
            parts.append(f"Noise: {room_data['noise_decibel']:.0f}dB")
        
        return ", ".join(parts) if parts else "No sensor readings"
    
    def _format_history(self, history: List[Dict]) -> str:
        """Format conversation history for the prompt."""
        if not history:
            return "No previous conversation"
        
        formatted = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prefix = "User" if role == "user" else "Assistant"
            formatted.append(f"{prefix}: {content}")
        
        return "\n".join(formatted)
    
    def _build_chat_prompt(
        self,
        context: Dict[str, Any],
        history: List[Dict],
        user_message: str
    ) -> str:
        """Build rich prompt with all baby context for insightful responses."""
        baby = context.get("baby")
        if not baby:
            return f"User: {user_message}\n\nPlease respond helpfully."
        
        age_str = self._format_age(baby)
        
        # Format correlations (awakening causes)
        correlations_text = ""
        if context.get("correlations"):
            causes = []
            for c in context["correlations"]:
                params = c.get("parameters", {})
                if params:
                    changes = []
                    for k, v in params.items():
                        if isinstance(v, dict):
                            direction = v.get('direction', 'changed')
                            percent = v.get('change_percent', 0)
                            changes.append(f"{k}: {direction} {percent:.0f}%")
                    if changes:
                        causes.append(f"- {c.get('time', 'Unknown')}: {', '.join(changes)}")
            if causes:
                correlations_text = "Recent awakening causes (sensor changes detected):\n" + "\n".join(causes[:5])
        
        # Format sleep patterns
        patterns_text = ""
        if context.get("sleep_patterns"):
            patterns = []
            for p in context["sleep_patterns"]:
                label = p.get('label', 'Sleep')
                start = p.get('avg_start', '??:??')
                end = p.get('avg_end', '??:??')
                duration = p.get('avg_duration_hours', 0)
                patterns.append(f"- {label}: {start} - {end} ({duration:.1f}h)")
            if patterns:
                patterns_text = "Typical sleep schedule this month:\n" + "\n".join(patterns)
        
        # Format daily stats
        stats_text = ""
        summaries = context.get("daily_summaries", [])
        if summaries:
            temps = [s.get("avg_temp") for s in summaries if s.get("avg_temp")]
            avg_temp = sum(temps) / len(temps) if temps else None
            
            total_awakenings = sum(
                (s.get("morning_awakes_sum") or 0) +
                (s.get("noon_awakes_sum") or 0) +
                (s.get("night_awakes_sum") or 0)
                for s in summaries
            )
            
            if avg_temp:
                stats_text = f"Last {len(summaries)} days: avg temp {avg_temp:.1f}°C, {total_awakenings} total awakenings"
        
        # Format recent awakenings
        awakenings_text = ""
        if context.get("recent_awakenings"):
            awakening_lines = []
            for a in context["recent_awakenings"][:3]:
                awakened_at = a.get("awakened_at")
                duration = a.get("sleep_duration_minutes", 0)
                insight = a.get("ai_insight", "")
                
                if awakened_at:
                    time_str = awakened_at.strftime("%m/%d %H:%M") if isinstance(awakened_at, datetime) else str(awakened_at)[:16]
                    hours = int(duration // 60)
                    mins = int(duration % 60)
                    duration_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
                    line = f"- {time_str}: slept {duration_str}"
                    if insight:
                        line += f" - {insight[:100]}..."
                    awakening_lines.append(line)
            
            if awakening_lines:
                awakenings_text = "Recent awakenings:\n" + "\n".join(awakening_lines)
        
        # Build optimal conditions text
        optimal = context.get("optimal_stats", {})
        optimal_text = ""
        if optimal:
            parts = []
            if optimal.get("temperature"):
                parts.append(f"Temperature: {optimal['temperature']:.1f}°C")
            if optimal.get("humidity"):
                parts.append(f"Humidity: {optimal['humidity']:.0f}%")
            if optimal.get("noise"):
                parts.append(f"Noise: {optimal['noise']:.0f}dB")
            if parts:
                optimal_text = "Optimal conditions (learned from best sleeps): " + ", ".join(parts)
        
        prompt = f"""You are a warm, knowledgeable pediatric sleep consultant helping parents with their baby {baby.first_name}.

=== BABY PROFILE ===
- Name: {baby.first_name} {baby.last_name}
- Age: {age_str}
- Parent notes: {context.get('notes') or 'None provided'}

=== {optimal_text or 'No optimal conditions learned yet'} ===

=== SLEEP STATISTICS ===
{patterns_text or 'No sleep patterns detected yet'}

{stats_text}

=== RECENT SLEEP HISTORY ===
{awakenings_text or 'No recent awakenings recorded'}

=== AWAKENING ANALYSIS ===
{correlations_text or 'No awakening correlations analyzed yet'}

=== CURRENT ROOM ===
{self._format_room(context.get('current_room'))}

=== CONVERSATION HISTORY ===
{self._format_history(history)}

User: {user_message}

Provide a helpful, personalized response based on {baby.first_name}'s specific data.

=== AGE-SPECIFIC SLEEP GUIDELINES (use these for {age_str}) ===

NEWBORNS (0-3 months):
- Total sleep: 14-17 hours/day in short periods
- Wake windows: 45-90 minutes max
- Naps: 4-6 naps, no set schedule yet
- Night sleep: 8-10 hours with frequent waking for feeds
- Key focus: Safe sleep (back to sleep, firm surface, bare crib), room sharing, feeding on demand
- Sleep training: NOT appropriate yet - focus on establishing routines
- Ideal room temp: 68-72°F (20-22°C)

INFANTS 3-6 MONTHS:
- Total sleep: 14-16 hours/day
- Wake windows: 1.5-2.5 hours
- Naps: 3-4 naps/day (4-6 hours total daytime sleep)
- Night sleep: 10-12 hours (may still wake 1-2x for feeds)
- Key focus: Establishing consistent bedtime routine, self-soothing introduction
- Sleep training: Can begin gentle methods around 4 months
- Watch for: 4-month sleep regression (normal developmental change)

INFANTS 6-9 MONTHS:
- Total sleep: 12-15 hours/day
- Wake windows: 2-3 hours
- Naps: 2-3 naps/day (3-4 hours total daytime sleep)
- Night sleep: 10-12 hours (many can sleep through)
- Key focus: Consistent schedule, dropping third nap around 8-9 months
- Sleep training: Most effective window
- Watch for: Separation anxiety affecting sleep, teething disruptions

INFANTS 9-12 MONTHS:
- Total sleep: 12-14 hours/day
- Wake windows: 2.5-3.5 hours
- Naps: 2 naps/day (2.5-3 hours total daytime sleep)
- Night sleep: 11-12 hours
- Key focus: Predictable 2-nap schedule, longer wake windows
- Watch for: Standing in crib, separation anxiety peaks

TODDLERS 12-24 MONTHS:
- Total sleep: 11-14 hours/day
- Wake windows: 4-6 hours
- Naps: Transition from 2 naps to 1 nap (12-18 months), 2-3 hours
- Night sleep: 10-12 hours
- Key focus: Single nap transition, consistent boundaries, bedtime routine
- Watch for: 18-month sleep regression, toddler resistance

RESPONSE GUIDELINES:
1. PRIORITIZE {baby.first_name}'s ACTUAL DATA above general guidelines:
   - Use the SLEEP PATTERNS section to understand their real schedule
   - Reference OPTIMAL CONDITIONS learned from their best sleeps
   - Consider AWAKENING ANALYSIS to identify specific issues
   - Factor in PARENT NOTES for health conditions/allergies
   - Check CURRENT ROOM conditions if environment questions arise

2. Use AGE GUIDELINES as supporting context:
   - Compare their actual patterns to age-appropriate expectations
   - If their data differs from guidelines, explain why that might be okay OR suggest adjustments
   - Tailor recommendations to what's developmentally appropriate for {age_str}

3. Communication style:
   - Be warm, supportive, and reassuring - parenting is hard!
   - Always cite specific data points when available (e.g., "Based on Oran's optimal temp of 22°C...")
   - Provide actionable, personalized recommendations
   - Keep responses concise (2-4 sentences) unless more detail is requested
   - If data is missing for a question, acknowledge it and give age-appropriate guidance"""
        
        return prompt
    
    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API and return response."""
        client = _get_gemini_client()
        
        if not client:
            return "I'm sorry, the AI service is currently unavailable. Please try again later."
        
        try:
            from google.genai import types
            
            loop = asyncio.get_event_loop()
            # Use configurable model (default: gemini-2.0-flash for better quality)
            model_name = settings.GEMINI_MODEL_CHAT
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7,  # Slightly more creative for chat
                        max_output_tokens=4096,  # Increased significantly to prevent truncation
                        top_p=0.9,
                    ),
                )
            )
            
            if response:
                # Log response details for debugging
                logger.debug(f"Gemini response object: {response}")
                
                # Check for blocked responses (safety filters)
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    logger.warning(f"Prompt feedback: {response.prompt_feedback}")
                
                # Try to get text from response
                if response.text:
                    text = response.text.strip()
                    # Check for potentially incomplete response
                    if text and text[-1] not in '.!?:)"\'':
                        logger.warning(f"Potentially incomplete chat response - may have been truncated")
                    return text
                
                # Try candidates if text is empty
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            text = candidate.content.parts[0].text.strip()
                            if text:
                                return text
                    # Check for finish reason
                    if hasattr(candidate, 'finish_reason'):
                        logger.warning(f"Response finish reason: {candidate.finish_reason}")
                
                logger.warning(f"Empty or blocked response from Gemini")
            
            return "I'm sorry, I couldn't generate a response. Please try again."
                
        except Exception as e:
            logger.error(f"Gemini API error in chat: {e}")
            return "I'm sorry, there was an error processing your request. Please try again."
    
    async def chat(
        self,
        baby_id: int,
        user_message: str,
        conversation_history: List[Dict]
    ) -> str:
        """
        Process a chat message with full baby context.
        
        Args:
            baby_id: The ID of the baby
            user_message: The user's message
            conversation_history: List of previous messages [{role, content}]
            
        Returns:
            AI-generated response string
        """
        # Limit history to prevent prompt blow-up
        history = conversation_history[-MAX_CHAT_HISTORY:] if conversation_history else []
        
        # Get full baby context
        context = await self.get_full_baby_context(baby_id)
        
        if not context.get("baby"):
            return "I couldn't find information about this baby. Please make sure you're logged in correctly."
        
        # Build prompt with all context
        prompt = self._build_chat_prompt(context, history, user_message)
        
        # Call Gemini and return response
        response = await self._call_gemini(prompt)
        
        logger.info(f"Chat response generated for baby {baby_id}")
        return response


# Singleton instance
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Get the chat service singleton."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
