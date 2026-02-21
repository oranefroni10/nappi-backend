"""
Centralized constants for the Nappi baby sleep monitoring system.

All domain thresholds, limits, and reference data are defined here with source citations.
Every value is backed by peer-reviewed research, clinical guidelines, or recognized
professional organizations. See inline comments for full citations.

IMPORTANT: Do NOT scatter magic numbers across service files. Import from here.
"""

# =============================================================================
# ENVIRONMENTAL THRESHOLDS — Alert Triggers
# =============================================================================

# Room temperature safe range for infant sleep (Celsius).
# Source: AAP (American Academy of Pediatrics) recommends 20-22.2°C (68-72°F).
#   - https://www.aap.org (safe sleep guidelines)
# Source: Wailoo et al., "The thermal environment in which 3-4 month old infants
#   sleep at home," Archives of Disease in Childhood, 1989 — thermal neutrality 20-22°C.
# Source: Franco et al., "Ambient Temperature is Associated with Changes in Infants'
#   Arousability from Sleep," Sleep, 2001 — at 24°C arousability increases.
# Alert boundaries are set slightly wider than the optimal range to avoid
# over-alerting while still catching genuinely unsafe conditions.
TEMP_ALERT_HIGH_C = 26.0   # Alert if room exceeds this
TEMP_ALERT_LOW_C = 18.0    # Alert if room drops below this

# Optimal temperature range used for environment status assessment.
# Narrower than alert thresholds — represents ideal conditions.
# Source: AAP recommends 20-22.2°C; Franco et al. 2001 shows 24°C increases arousability.
TEMP_OPTIMAL_HIGH_C = 24.0
TEMP_OPTIMAL_LOW_C = 20.0

# Humidity safe range for infant sleep (%).
# Source: AAP recommends 40-60% for infants under one year.
#   - Prevents dryness (chapped lips, dry skin, irritated nasal passages) below 40%.
#   - Above 60% encourages mold growth and dust mites.
# Source: EPA indoor air quality guidelines also recommend 30-50% relative humidity.
# Alert boundaries match AAP guidance; optimal is the tighter EPA range.
HUMIDITY_ALERT_HIGH_PCT = 60.0   # Alert if humidity exceeds this
HUMIDITY_ALERT_LOW_PCT = 30.0    # Alert if humidity drops below this
HUMIDITY_OPTIMAL_HIGH_PCT = 60.0
HUMIDITY_OPTIMAL_LOW_PCT = 40.0

# Noise level limit for infant sleep (dB A-weighted).
# Source: Hugh et al., "Infant Sleep Machines and Hazardous Sound Pressure Levels,"
#   Pediatrics, 2014 — hospital nursery recommendation: average 50 dB over 1 hour.
#   13 of 14 infant sleep machines exceeded 50 dB at 100cm.
NOISE_ALERT_HIGH_DB = 50.0   # Alert if noise exceeds this


# =============================================================================
# HEALTHY RANGES — Used in AI prompts for context
# =============================================================================

# These represent the ideal ranges communicated to the AI for insight generation.
# Source: Same as above — AAP, Wailoo 1989, Franco 2001, Hugh 2014.
HEALTHY_RANGES = {
    "temp_celcius": {
        "name": "Temperature",
        "unit": "°C",
        "min": TEMP_OPTIMAL_LOW_C,    # 20°C — AAP + Wailoo 1989
        "max": TEMP_OPTIMAL_HIGH_C,   # 24°C — Franco 2001 arousability threshold
    },
    "humidity": {
        "name": "Humidity",
        "unit": "%",
        "min": HUMIDITY_OPTIMAL_LOW_PCT,   # 40% — AAP
        "max": HUMIDITY_OPTIMAL_HIGH_PCT,  # 60% — AAP
    },
    "noise_decibel": {
        "name": "Noise",
        "unit": "dB",
        "min": 0.0,
        "max": NOISE_ALERT_HIGH_DB,   # 50 dB — Hugh et al. 2014
    },
}


# =============================================================================
# COOLDOWN DURATIONS
# =============================================================================

# Minimum minutes between repeated alerts of the same type for the same baby.
# Prevents notification spam when a sensor stays in the alert zone.
ALERT_COOLDOWN_MINUTES = 5

# Minutes to ignore sensor sleep-start/sleep-end events after a parent
# manually overrides the sleep state (mark_asleep / mark_awake).
# Gives the parent's action time to take effect before sensors resume control.
INTERVENTION_COOLDOWN_MINUTES = 20


# =============================================================================
# SLEEP ANALYSIS PARAMETERS
# =============================================================================

# Gap threshold for grouping consecutive awakening events into a single sleep block.
# If the gap between two events is > this, they belong to different blocks.
# Source: Domain heuristic — 30 minutes accounts for brief re-settling.
SLEEP_BLOCK_GAP_THRESHOLD_MINUTES = 30

# Gap threshold for clustering sleep sessions by time-of-day similarity.
# Sessions starting > 2 hours apart are assigned to different clusters.
# Source: Domain heuristic — separates morning nap, afternoon nap, night sleep.
SLEEP_PATTERN_GAP_HOURS = 2.0

# Trend analysis: percentage change threshold to classify as "improving" or "declining".
# Compares first half vs second half of the analysis period.
# Source: Domain heuristic — 5% avoids noise while catching meaningful change.
TREND_IMPROVING_THRESHOLD_PCT = 5.0
TREND_DECLINING_THRESHOLD_PCT = -5.0

# Consistency score multiplier: score = 100 - (std_dev * this), clamped to 0-100.
# Higher multiplier = more sensitive to variation.
CONSISTENCY_STD_DEV_MULTIPLIER = 10.0

# Optimal stats weighting: weight = 1 / (1 + total_awakenings).
# Days with fewer awakenings contribute more to the "optimal" environment.
# Source: Domain logic — inverse weighting by disruptions.
OPTIMAL_STATS_WEIGHT_BASE = 1.0


# =============================================================================
# CORRELATION ANALYSIS
# =============================================================================

# Per-sensor percentage change thresholds for flagging significant changes.
# Compares the average of the first 25% of readings vs last 25% before awakening.
# Source: Domain heuristic — temp/humidity sensitive at 5%; noise needs >100% to matter.
CORRELATION_CHANGE_THRESHOLDS = {
    "temp_celcius": 5.0,
    "humidity": 5.0,
    "noise_decibel": 100.0,
}

# Fraction of sensor readings to compare (first quarter vs last quarter).
CORRELATION_QUARTILE_FRACTION = 0.25

# Default time window (minutes) to look back for sensor data before an awakening.
CORRELATION_TIME_WINDOW_MINUTES = 60


# =============================================================================
# TIME-OF-DAY CLASSIFICATIONS
# =============================================================================

# Used for daily summary awakening counts (morning / noon / night).
# Source: Standard pediatric day segmentation.
DAILY_SUMMARY_MORNING_START = 6    # 6 AM
DAILY_SUMMARY_MORNING_END = 12     # 12 PM
DAILY_SUMMARY_NOON_START = 12      # 12 PM
DAILY_SUMMARY_NOON_END = 18        # 6 PM
# Night = 18:00 to 06:00 (spans midnight)

# Used for AI prompt context (correlation analyzer, trend analyzer).
AI_MORNING_START = 5
AI_MORNING_END = 12
AI_AFTERNOON_START = 12
AI_AFTERNOON_END = 17
AI_EVENING_START = 17
AI_EVENING_END = 21
# Night = 21:00 to 05:00

# Used for sleep pattern cluster labels.
PATTERN_MORNING_START = 5
PATTERN_MORNING_END = 11
PATTERN_AFTERNOON_START = 11
PATTERN_AFTERNOON_END = 17
# Night = everything else


# =============================================================================
# AGE-BASED SLEEP RECOMMENDATIONS
# =============================================================================

# Sleep duration recommendations (hours per 24-hour period) by age group.
# Source: National Sleep Foundation (NSF), Hirshkowitz et al., "National Sleep
#   Foundation's updated sleep duration recommendations," Sleep Health, 2015.
# Source: American Academy of Sleep Medicine (AASM) consensus statement, 2016.
# Source: Sadeh et al., "Sleep and sleep ecology in the first 3 years: a web-based
#   study," Journal of Sleep Research, 2009 — Table 2.
# Source: Bhargava, "Diagnosis and Management of Common Sleep Problems in Children,"
#   Pediatrics in Review, 2011 — Table 1.
# Format: (age_min_months, age_max_months): (min_hours, max_hours, typical_naps, night_hours)
AGE_SLEEP_RECOMMENDATIONS = {
    (0, 3):   {"min_hours": 14, "max_hours": 17, "typical_naps": "4-5", "night_hours": "8-9"},
    (4, 6):   {"min_hours": 12, "max_hours": 16, "typical_naps": "3-4", "night_hours": "9-10"},
    (7, 12):  {"min_hours": 12, "max_hours": 15, "typical_naps": "2-3", "night_hours": "10-11"},
    (13, 24): {"min_hours": 11, "max_hours": 14, "typical_naps": "1-2", "night_hours": "10-12"},
    (25, 36): {"min_hours": 10, "max_hours": 13, "typical_naps": "0-1", "night_hours": "10-12"},
}


# =============================================================================
# WAKE WINDOWS BY AGE
# =============================================================================

# Recommended awake time between sleep sessions (hours) by age.
# Source: Cleveland Clinic, "Wake Windows by Age,"
#   https://health.clevelandclinic.org/wake-windows-by-age
# Format: (age_min_months, age_max_months): (min_hours, max_hours)
WAKE_WINDOWS = {
    (0, 1):   (0.5, 1.0),    # Birth to 1 month: 30-60 min
    (1, 3):   (1.0, 2.0),    # 1-3 months: 1-2 hours
    (3, 4):   (1.25, 2.5),   # 3-4 months: 1.25-2.5 hours
    (5, 7):   (2.0, 4.0),    # 5-7 months: 2-4 hours
    (7, 10):  (2.5, 4.5),    # 7-10 months: 2.5-4.5 hours
    (10, 12): (3.0, 6.0),    # 10-12 months: 3-6 hours
    (13, 18): (3.0, 5.5),    # 13-18 months: ~3-5.5 hours (extrapolated)
    (19, 24): (4.0, 6.0),    # 19-24 months: ~4-6 hours (extrapolated)
    (25, 36): (5.0, 6.0),    # 25-36 months: ~5-6 hours (extrapolated)
}


# =============================================================================
# TYPICAL BEDTIMES BY AGE
# =============================================================================

# Age-appropriate bedtime ranges.
# Source: Cleveland Clinic, "Sleep in Your Baby's First Year,"
#   https://my.clevelandclinic.org/health/articles/14300-sleep-in-your-babys-first-year
# Source: AAP safe sleep guidelines.
# Format: (age_min_months, age_max_months): (earliest_hour, earliest_min, latest_hour, latest_min)
TYPICAL_BEDTIMES = {
    (0, 3):   (20, 0, 23, 0),    # 8:00 PM - 11:00 PM
    (4, 6):   (19, 0, 20, 30),   # 7:00 PM - 8:30 PM
    (7, 12):  (18, 30, 20, 0),   # 6:30 PM - 8:00 PM
    (13, 24): (19, 0, 20, 0),    # 7:00 PM - 8:00 PM
    (25, 36): (19, 0, 20, 30),   # 7:00 PM - 8:30 PM
}


# =============================================================================
# SCHEDULE PREDICTION PARAMETERS
# =============================================================================

# Multipliers for determining wake window status relative to expected window.
# Source: Domain heuristic.
WAKE_WINDOW_RECENTLY_WOKE_FACTOR = 0.8    # < 80% of min → "recently woke"
WAKE_WINDOW_APPROACHING_FACTOR = 1.2      # > 120% of max → "overdue"

# Fallback prediction offsets (minutes from now) when no pattern data.
PREDICTION_FALLBACK_APPROACHING_MINUTES = 15
PREDICTION_FALLBACK_OVERDUE_MINUTES = 30

# Age threshold (months) for switching from nap-based to bedtime-based prediction.
BEDTIME_PREDICTION_AGE_THRESHOLD_MONTHS = 12

# Fallback nap times (hour, minute) when insufficient pattern data.
# Used by time of day: before 10 AM, before 13, before 15, before 18, else.
FALLBACK_NAP_TIMES = [
    (10, 10, 30),   # Before 10:00 AM → predict 10:30
    (13, 13, 30),   # Before 1:00 PM → predict 13:30
    (15, 16, 0),    # Before 3:00 PM → predict 16:00
    (18, 18, 30),   # Before 6:00 PM → predict 18:30
]
# After 6:00 PM → bedtime prediction (age-dependent: 19:00 or 20:00)


# =============================================================================
# PAGINATION & CONTEXT LIMITS
# =============================================================================

# Alert history — default page size.
ALERTS_DEFAULT_PAGE_SIZE = 50

# Chat service — context window limits to prevent Gemini prompt blow-up.
CHAT_MAX_NOTES_CHARS = 1000
CHAT_MAX_HISTORY_MESSAGES = 10
CHAT_MAX_AWAKENINGS = 5
CHAT_MAX_CORRELATIONS = 5
CHAT_MAX_SUMMARY_DAYS = 7

# Correlation analyzer — notes truncation for AI prompt.
CORRELATION_MAX_NOTES_CHARS = 1000

# Stats API — date range limits.
STATS_MIN_DAYS = 7
STATS_MAX_DAYS = 90


# =============================================================================
# NETWORK TIMEOUTS
# =============================================================================

# Timeout (seconds) for live HTTP sensor fetch from M5 devices.
SENSOR_FETCH_TIMEOUT_SECONDS = 5

# SSE keepalive ping interval (seconds) — prevents proxy/browser timeout.
SSE_KEEPALIVE_SECONDS = 30


# =============================================================================
# GEMINI AI GENERATION PARAMETERS
# =============================================================================

# Temperature controls randomness: 0.0 = deterministic, 1.0 = creative.
# top_p controls nucleus sampling: lower = more focused.
# max_output_tokens caps response length.

GEMINI_INSIGHTS_TEMPERATURE = 0.0
GEMINI_INSIGHTS_MAX_TOKENS = 2048
GEMINI_INSIGHTS_TOP_P = 0.9

GEMINI_QUICK_INSIGHT_TEMPERATURE = 0.0
GEMINI_QUICK_INSIGHT_MAX_TOKENS = 512

GEMINI_TRENDS_TEMPERATURE = 0.3
GEMINI_TRENDS_MAX_TOKENS = 600

# Chat — more creative for conversational AI.
GEMINI_CHAT_TEMPERATURE = 0.3
GEMINI_CHAT_MAX_TOKENS = 4096
GEMINI_CHAT_TOP_P = 0.9

# Today's tip — deterministic, very concise.
GEMINI_TIP_TEMPERATURE = 0.0
GEMINI_TIP_MAX_TOKENS = 150


# =============================================================================
# SLEEP CHART THRESHOLDS (shared with frontend)
# =============================================================================

# Daily sleep duration color coding thresholds (hours).
# Source: NSF recommendations — 12+ hours is excellent for most infants,
#   10-12 is adequate, <10 is below recommended.
SLEEP_EXCELLENT_THRESHOLD_HOURS = 12
SLEEP_GOOD_THRESHOLD_HOURS = 10

# Age-based calculation: approximate days per month.
DAYS_PER_MONTH = 30
