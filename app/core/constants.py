"""Clinical thresholds, age-based recommendations, and app-level tuning constants."""

# ── TEMPERATURE THRESHOLDS ────────────────────────────────────────────────────
# source: Franco et al., "Ambient Temperature is Associated with Changes in Infants' Arousability from Sleep," SLEEP Vol.24 No.3, 2001, pp.325-329
# place:  p.325 col.2 para.2 (Methods → Monitoring Procedures), p.325 col.2 Abstract, p.329 col.1 last para (Discussion)
# quotes:
#   1. "The lower critical temperature corresponding to the thermal neutrality range was defined as 20-22°C." (p.325)
#   2. "it can be postulated that overheating adds to the difficulty to arouse from sleep, particularly during the late hours of the night, when most SIDS deaths occur." (p.329)
#
#
# source: NHS UK, "Reduce the risk of sudden infant death syndrome"
#         https://www.nhs.uk/conditions/baby/caring-for-a-newborn/reduce-the-risk-of-sudden-infant-death-syndrome/
# place:  section "How to make sure your baby doesn't get too hot or cold", bullet 1 under "To reduce the risk of SIDS:"
# quotes:
#   1. "keep the room at a temperature between about 16 to 20C – monitor the temperature using a room thermometer"
#
# NOTE on values chosen:
#   Optimal low 20°C = lower bound of Franco's thermal neutrality (20-22°C).
#   Optimal high 24°C = Franco's safe experimental condition (arousal normal at 24°C,
#     impaired at 28°C), engineering choice - no source prescribes 24°C as a limit.
#   Alert high 26°C = engineering midpoint between Franco's 24°C and 28°C, no source
#     cites 26°C directly.
#     NHS lower bound is 16°C, so 18°C is within the NHS safe range.
TEMP_ALERT_HIGH_C = 26.0
TEMP_ALERT_LOW_C = 18.0

TEMP_OPTIMAL_HIGH_C = 24.0
TEMP_OPTIMAL_LOW_C = 20.0

# ── HUMIDITY THRESHOLDS ──────────────────────────────────────────────────────
# source: U.S. EPA, "Care for Your Air: A Guide to Indoor Air Quality"
#         https://www.epa.gov/indoor-air-quality-iaq/care-your-air-guide-indoor-air-quality
# place:  section "Improving Your Indoor Air → Adjusting humidity", para.2
# quotes:
#   1. "Keep indoor humidity between 30 and 50 percent."
#
# source: Bhargava S, "Diagnosis and Management of Common Sleep Problems in Children," Pediatrics in Review, 2011,32(3):91-99
# place:  p.93 col.1 para.3 (Management of sleep-onset association type)
# quotes (general environment - no humidity numbers in this paper):
#   1. "The bedroom should be dark, cool, and quiet because this is the most conducive environment for sleep."
#
# NOTE on values chosen:
#   Alert low 30% and alert high 60% = EPA guidance ("between 30 and 50 percent"
#     with a ceiling of 60% per EPA Mold Course Ch.9, took some safe distance).
#   Optimal low 40% = engineering choice for infant comfort, no cited source specifies
#     40% as a lower bound. EPA ideal starts at 30%.
#   Optimal high 60% = EPA hard ceiling, EPA's ideal upper bound is actually 50%.
HUMIDITY_ALERT_HIGH_PCT = 60.0
HUMIDITY_ALERT_LOW_PCT = 30.0
HUMIDITY_OPTIMAL_HIGH_PCT = 50.0
HUMIDITY_OPTIMAL_LOW_PCT = 40.0

# ── NOISE THRESHOLD ──────────────────────────────────────────────────────────
# source: Hugh et al., "Infant Sleep Machines and Hazardous Sound Pressure Levels," Pediatrics, 2014,133(4):677-681
# place:  p.678 col.2 last para of Introduction, p.677 Abstract → Results, p.679 col.1 Results para.2
# quotes:
#   1. "a 50-dBA-equivalent noise level averaged over 1 hour has been recommended as a maximum safe exposure for infants in hospital nurseries and NICUs." (p.678)
#   2. "Maximum sound levels at 30 cm were >50 A-weighted dB for all devices, which is the current recommended noise limit for infants in hospital nurseries." (p.677 Abstract)
#   3. "All 14 ISMs were capable of producing noise >50 dBA at distances of 30 and 100 cm." (p.679)
#
# source: WHO, "Night Noise Guidelines for Europe," 2009
#         https://www.who.int/europe/publications/i/item/9789289041737
# place:  p.xv Executive Summary
# quotes:
#   1. "Lnight,outside of 40 dB should be the target of the night noise guideline (NNG) to protect the public, including the most vulnerable groups such as children [...]"
#   NOTE: WHO target is 40 dB for outdoor annual-average noise - a different
#   measurement context from the 50 dB indoor nursery limit from Hugh et al.
NOISE_ALERT_HIGH_DB = 50.0


HEALTHY_RANGES = {
    "temp_celcius": {
        "name": "Temperature",
        "unit": "°C",
        "min": TEMP_OPTIMAL_LOW_C,
        "max": TEMP_OPTIMAL_HIGH_C,
    },
    "humidity": {
        "name": "Humidity",
        "unit": "%",
        "min": HUMIDITY_OPTIMAL_LOW_PCT,
        "max": HUMIDITY_OPTIMAL_HIGH_PCT,
    },
    "noise_decibel": {
        "name": "Noise",
        "unit": "dB",
        "min": 0.0,
        "max": NOISE_ALERT_HIGH_DB,
    },
}


# No clinical source, app-level UX cooldowns.
ALERT_COOLDOWN_MINUTES = 5
INTERVENTION_COOLDOWN_MINUTES = 20


# ── SLEEP BLOCK / PATTERN DETECTION ─────────────────────────────────────────
# Engineering choice, no paper directly prescribes a 30-minute gap for splitting
# sleep blocks. Value informed by common actigraphy practice but not directly
# cited from any single source.
SLEEP_BLOCK_GAP_THRESHOLD_MINUTES = 30

# Engineering choice, no paper prescribes a 2-hour gap. Value informed by the
# day/night boundary used in Sadeh et al. (2009):
# source: Sadeh et al., "Sleep and sleep ecology in the first 3 years," J Sleep Res, 2009,18:60-73
# place:  p.62 col.1 Measures para.1
# quotes:
#   1. "daytime sleep (between 8:00 and 19:00 hours, in hours)" (p.62)
#   2. "nighttime sleep (between 19:00 and 8:00 hours, in hours)" (p.62)
SLEEP_PATTERN_GAP_HOURS = 2.0

# No clinical source, app-level statistical + engineering choices.
TREND_IMPROVING_THRESHOLD_PCT = 5.0
TREND_DECLINING_THRESHOLD_PCT = -5.0
CONSISTENCY_STD_DEV_MULTIPLIER = 10.0
OPTIMAL_STATS_WEIGHT_BASE = 1.0


CORRELATION_CHANGE_THRESHOLDS = {
    "temp_celcius": 5.0,
    "humidity": 5.0,
    "noise_decibel": 100.0,
}
CORRELATION_QUARTILE_FRACTION = 0.25
CORRELATION_TIME_WINDOW_MINUTES = 60


# No clinical source, conventional day partitioning for summaries + AI.
DAILY_SUMMARY_MORNING_START = 6
DAILY_SUMMARY_MORNING_END = 12
DAILY_SUMMARY_NOON_START = 12
DAILY_SUMMARY_NOON_END = 18

AI_MORNING_START = 5
AI_MORNING_END = 12
AI_AFTERNOON_START = 12
AI_AFTERNOON_END = 17
AI_EVENING_START = 17
AI_EVENING_END = 21

PATTERN_MORNING_START = 5
PATTERN_MORNING_END = 11
PATTERN_AFTERNOON_START = 11
PATTERN_AFTERNOON_END = 17


# ── AGE-BASED SLEEP RECOMMENDATIONS ─────────────────────────────────────────
# min_hours / max_hours:
# source: Hirshkowitz et al., "National Sleep Foundation's sleep time duration recommendations," Sleep Health, 2015,1(1):40-43
# place:  p.42, Table 2 "Recommended" column
# data:
#   1. Newborns 0-3 months → Recommended: 14-17 (Table 2 row 1)
#   2. Infants 4-11 months → Recommended: 12-15 (Table 2 row 2)
#   3. Toddlers 1-2 years → Recommended: 11-14, Preschoolers 3-5 years → Recommended: 10-13 (Table 2 rows 3-4)
#
# source: Tham et al., "Infant sleep and its relation with cognition and growth," Nature and Science of Sleep, 2017,9:135-149
# place:  p.136 col.1 para.2
# quotes:
#   1. "The National Sleep Foundation (NSF) recommends a daily sleep duration of 14–17 hours/day from birth to 3 months, 12–15 hours/day from 4 to 11 months, 11–14 hours/day for infants aged 1–2 years, and 10–13 hours/day for preschoolers aged 3–5 years."
#
# typical_naps / night_hours:
# source: Sadeh et al., "Sleep and sleep ecology in the first 3 years," J Sleep Res, 2009,18:60-73
# place:  p.63, Table 2 "Sleep measures across age groups" (n=5006)
# data:
#   1. 0-2m:   Naps(N) 3.59±1.18  Nighttime sleep(h) 8.50±1.83 (Table 2 row 1)
#   2. 3-5m:   Naps(N) 2.93±0.83  Nighttime sleep(h) 9.47±1.55 (Table 2 row 2)
#   3. 6-8m:   Naps(N) 2.42±0.75  Nighttime sleep(h) 9.86±1.44 (Table 2 row 3)
#   4. 9-11m:  Naps(N) 2.02±0.52  Nighttime sleep(h) 9.92±1.45 (Table 2 row 4)
#   5. 12-17m: Naps(N) 1.53±0.55  Nighttime sleep(h) 10.3±1.39 (Table 2 row 5)
#   6. 18-23m: Naps(N) 1.11±0.34  Nighttime sleep(h) 10.3±1.26 (Table 2 row 6)
#   7. 24-36m: Naps(N) 0.92±0.37  Nighttime sleep(h) 10.0±1.30 (Table 2 row 7)
#
# NOTE: NSF defines one 4-11 month band, the (4,6)/(7,12) split below is a UX
# design choice to pair age groups with different nap/night patterns from Sadeh.
# night_hours values are the mean rounded to nearest integers - actual variability
# is ±1.3-1.8h (see SDs above).
AGE_SLEEP_RECOMMENDATIONS = {
    (0, 3):   {"min_hours": 14, "max_hours": 17, "typical_naps": "3-5", "night_hours": "8-9"},
    (4, 6):   {"min_hours": 12, "max_hours": 15, "typical_naps": "2-3", "night_hours": "9-10"},
    (7, 12):  {"min_hours": 12, "max_hours": 15, "typical_naps": "2-3", "night_hours": "10-11"},
    (13, 24): {"min_hours": 11, "max_hours": 14, "typical_naps": "1-2", "night_hours": "10-12"},
    (25, 36): {"min_hours": 10, "max_hours": 13, "typical_naps": "0-1", "night_hours": "10-12"},
}


# ── WAKE WINDOWS (hours) ────────────────────────────────────────────────────
# Clinical heuristics informed by Sadeh et al. (2009) Table 2 data.
# Not directly derivable from a single formula - ranges are approximate.
#
# source: Sadeh et al., "Sleep and sleep ecology in the first 3 years," J Sleep Res, 2009,18:60-73
# place:  p.63, Table 2 - columns "Daytime sleep (h)" and "Naps (N)"
# data:
#   1. 0-2m:  Daytime sleep 5.75±2.28h, Naps 3.59±1.18 (Table 2 row 1)
#   2. 3-5m:  Daytime sleep 3.79±1.61h, Naps 2.93±0.83 (Table 2 row 2)
#   3. 9-11m: Daytime sleep 2.82±1.04h, Naps 2.02±0.52 (Table 2 row 4)
#   4. 24-36m: Daytime sleep 1.89±0.95h, Naps 0.92±0.37 (Table 2 row 7)
#
# NOTE: Specific (min, max) ranges below are engineering approximations, not
# a direct formula output. The data informs the ballpark, the ranges are rounded
# clinical heuristics with a buffer for individual variability.
WAKE_WINDOWS = {
    (0, 1):   (0.5, 1.0),
    (1, 3):   (1.0, 2.0),
    (3, 4):   (1.25, 2.5),
    (5, 7):   (2.0, 4.0),
    (7, 10):  (2.5, 4.5),
    (10, 12): (3.0, 6.0),
    (13, 18): (3.0, 5.5),
    (19, 24): (4.0, 6.0),
    (25, 36): (5.0, 6.0),
}


# ── TYPICAL BEDTIMES (earliest_h, earliest_m, latest_h, latest_m) ───────────
# Clinical heuristics. No cited source provides clock-time bedtime ranges by
# age group. Values are informed by the data below but not directly derived.
#
# source: Sadeh et al., "Sleep and sleep ecology in the first 3 years," J Sleep Res, 2009,18:60-73
# place:  p.62 col.1 Measures para.1, p.63 Table 2
# quotes:
#   1. "nighttime sleep (between 19:00 and 8:00 hours, in hours)" (p.62)
# data:
#   2. 0-2m Nighttime sleep 8.50±1.83h → bedtime ≈ 23:30 if waking at 08:00 (Table 2 row 1)
#   3. 24-36m Nighttime sleep 10.0±1.30h → bedtime ≈ 22:00 if waking at 08:00 (Table 2 row 7)
#
# source: Adams EL, Savage JS, Master L, Buxton OM, "Time for bed! Earlier sleep onset is associated with longer nighttime sleep duration during infancy," Sleep Medicine, 2020,73:58-63
#         https://doi.org/10.1016/j.sleep.2020.07.042
# place:  Abstract → Results, Results section "Sleep onset time"
# quotes:
#   1. "for every one hour earlier that infants fell asleep, their nighttime total sleep time was 34.4 minutes longer" (Abstract)
#   2. "On 24% of nights, infants fell asleep between 7:00-8:00 PM" (Results)
#
# NOTE: Specific bedtime ranges below (e.g. 18:30-20:00 for 7-12m) are
# engineering estimates, not values reported by any single study.
TYPICAL_BEDTIMES = {
    (0, 3):   (20, 0, 23, 0),
    (4, 6):   (19, 0, 20, 30),
    (7, 12):  (18, 30, 20, 0),
    (13, 24): (19, 0, 20, 0),
    (25, 36): (19, 0, 20, 30),
}


# No clinical source, app-level prediction tuning factors.
WAKE_WINDOW_RECENTLY_WOKE_FACTOR = 0.8
WAKE_WINDOW_APPROACHING_FACTOR = 1.2
PREDICTION_FALLBACK_APPROACHING_MINUTES = 15
PREDICTION_FALLBACK_OVERDUE_MINUTES = 30

# Engineering choice informed by nap consolidation data:
# source: Sadeh et al., J Sleep Res, 2009,18:60-73
# place:  p.63 Table 2, row 5 (12-17 months)
# data:
#   1. 9-11m Naps(N) 2.02±0.52 → 12-17m Naps(N) 1.53±0.55 (Table 2 rows 4-5)
#   Developer reasoning: nap count drops below 2 around 12 months, coinciding
#   with more predictable nighttime sleep. This threshold is an engineering
#   choice, not a clinical recommendation from the source.
BEDTIME_PREDICTION_AGE_THRESHOLD_MONTHS = 12

# No clinical source, fallback nap schedule consistent with Sadeh (2009) Table 2 nap counts.
FALLBACK_NAP_TIMES = [
    (10, 10, 30),
    (13, 13, 30),
    (15, 16, 0),
    (18, 18, 30),
]


# No clinical source, app-level pagination / truncation / timeout limits.
ALERTS_DEFAULT_PAGE_SIZE = 50
CHAT_MAX_NOTES_CHARS = 1000
CHAT_MAX_HISTORY_MESSAGES = 10
CHAT_MAX_AWAKENINGS = 5
CHAT_MAX_CORRELATIONS = 5
CHAT_MAX_SUMMARY_DAYS = 7
CORRELATION_MAX_NOTES_CHARS = 1000
STATS_MIN_DAYS = 7
STATS_MAX_DAYS = 90
SENSOR_FETCH_TIMEOUT_SECONDS = 5
SSE_KEEPALIVE_SECONDS = 30


# No clinical source, LLM inference tuning parameters.
GEMINI_INSIGHTS_TEMPERATURE = 0.0
GEMINI_INSIGHTS_MAX_TOKENS = 2048
GEMINI_INSIGHTS_TOP_P = 0.9
GEMINI_QUICK_INSIGHT_TEMPERATURE = 0.0
GEMINI_QUICK_INSIGHT_MAX_TOKENS = 512
GEMINI_TRENDS_TEMPERATURE = 0.3
GEMINI_TRENDS_MAX_TOKENS = 600
GEMINI_CHAT_TEMPERATURE = 0.3
GEMINI_CHAT_MAX_TOKENS = 4096
GEMINI_CHAT_TOP_P = 0.9
GEMINI_TIP_TEMPERATURE = 0.0
GEMINI_TIP_MAX_TOKENS = 150


# ── SLEEP QUALITY THRESHOLDS ─────────────────────────────────────────────────
# source: Hirshkowitz et al., Sleep Health, 2015,1(1):40-43
# place:  p.42, Table 2 "Recommended" column
# data:
#   1. Infants 4-11 months → Recommended: 12-15 - 12h is the lower bound.
#
# source: Tham et al., Nature and Science of Sleep, 2017,9:135-149
# place:  p.141 col.1, "Weight gain and obesity measures" section, para.1
# quotes:
#   1. "infant sleep of <12 hours/day in the first 2 years of life was associated with a higher body mass index (BMI), skinfold thickness, and an increased risk of being overweight at 3 years"
#
# source: Sadeh et al., J Sleep Res, 2009,18:60-73
# place:  p.66 col.1 para.1 (Discussion → Sleep patterns)
# quotes:
#   1. "during the 3–11 months age period, the 5th percentile of total sleep time is between 9 and 10 h"
#
# NOTE: These thresholds are age-independent. For newborns (0-3m, recommended
# 14-17h) 12h is below the minimum recommendation. For toddlers (1-2y,
# recommended 11-14h) 10h is also below minimum. These are rough heuristics,
# not age-specific clinical cutoffs.
SLEEP_EXCELLENT_THRESHOLD_HOURS = 12
SLEEP_GOOD_THRESHOLD_HOURS = 10

# No clinical source, standard calendar approximation.
DAYS_PER_MONTH = 30
