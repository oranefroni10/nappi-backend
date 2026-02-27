"""Seeds DB with 90 days of demo data. WARNING: Deletes existing data."""
import asyncio
import json
import math
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Tuple, Optional

from sqlalchemy import text

from app.core.database import get_database
from app.core.settings import settings
from app.core.constants import (
    OPTIMAL_STATS_WEIGHT_BASE,
    CORRELATION_CHANGE_THRESHOLDS,
    CORRELATION_QUARTILE_FRACTION,
)


SEED = 42
NOW = datetime.now()
DAYS_OF_DATA = 90
SENSOR_INTERVAL_MINUTES = 5
BATCH_SIZE = 500

# Sensor clamping ranges
TEMP_MIN, TEMP_MAX = 18.0, 26.0
HUMIDITY_MIN, HUMIDITY_MAX = 35.0, 70.0
NOISE_MIN, NOISE_MAX = 25.0, 55.0

# Progressive baseline targets (day 1 -> day 90)
PROGRESSION = {
    "temp_start": 23.0,
    "temp_end": 21.0,
    "humidity_start": 55.0,
    "humidity_end": 50.0,
    "noise_start": 40.0,
    "noise_end": 35.0,
    "variance_start": 0.5,
    "variance_end": 0.2,
    "spike_chance_start": 0.08,
    "spike_chance_end": 0.02,
}

# Awakening ranges per age: (start_min, start_max) -> (end_min, end_max)
AWAKENING_PROGRESSION = {
    "newborn": {"start": (3, 5), "end": (2, 3)},
    "infant": {"start": (2, 4), "end": (1, 2)},
    "toddler": {"start": (1, 3), "end": (0, 1)},
}

# Night cooling: hours 0-6 get this temp offset
NIGHT_COOLING_MIN = -1.0
NIGHT_COOLING_MAX = -0.3

# Weekend adjustments (minutes, dB, °C)
WEEKEND_BEDTIME_SHIFT_MIN = 15
WEEKEND_BEDTIME_SHIFT_MAX = 30
WEEKEND_NOISE_BOOST = 1.5
WEEKEND_TEMP_BOOST = 0.3

# ~40% of awakenings get sensor drift in last 30 min (6 readings at 5-min intervals)
DRIFT_INJECTION_CHANCE = 0.40
DRIFT_READINGS_COUNT = 6

# Alert read probability by age
ALERT_READ_OLD = 0.80
ALERT_READ_RECENT = 0.50
ALERT_READ_NEW = 0.20


BABIES_DATA = [
    {
        "first_name": "Emma",
        "last_name": "Cohen",
        "birthdate": NOW.date() - timedelta(days=90),
        "gender": "female",
        "age_category": "newborn",
        "notes_theme": "newborn_reflux",
    },
    {
        "first_name": "Noah",
        "last_name": "Levy",
        "birthdate": NOW.date() - timedelta(days=210),
        "gender": "male",
        "age_category": "infant",
        "notes_theme": "teething",
    },
    {
        "first_name": "Mia",
        "last_name": "Ben-David",
        "birthdate": NOW.date() - timedelta(days=420),
        "gender": "female",
        "age_category": "toddler",
        "notes_theme": "eczema",
    },
]

USERS_DATA = [
    {
        "username": "demo@nappi.app",
        "password": "demo123",
        "first_name": "Sarah",
        "last_name": "Cohen",
        "baby_index": 0,
    },
    {
        "username": "david@nappi.app",
        "password": "david123",
        "first_name": "David",
        "last_name": "Levy",
        "baby_index": 1,
    },
    {
        "username": "maya@nappi.app",
        "password": "maya123",
        "first_name": "Maya",
        "last_name": "Ben-David",
        "baby_index": 2,
    },
]

BABY_NOTES_DATA = {
    "newborn_reflux": [
        {"title": "Allergies", "content": "No known allergies yet, exclusively breastfed"},
        {"title": "Health Conditions", "content": "Mild reflux - keep upright 20min after feeding. Use inclined position for sleep."},
        {"title": "Sleep Preferences", "content": "Prefers white noise at low volume. Must be swaddled for naps. Loves the sound of the washing machine."},
        {"title": "Feeding Schedule", "content": "Feeds every 2-3 hours. Last feed at 7:30pm before bedtime."},
    ],
    "teething": [
        {"title": "Allergies", "content": "Slight sensitivity to cow's milk - using hypoallergenic formula"},
        {"title": "Health Conditions", "content": "Currently teething (bottom front teeth). Gets fussy in the evenings."},
        {"title": "Sleep Training", "content": "Started sleep training 2 weeks ago. Working on self-soothing - wait 5 min before intervening."},
        {"title": "Comfort Items", "content": "Has a favorite blue elephant stuffed animal. Uses teething ring before bed."},
        {"title": "Nap Schedule", "content": "Takes 2 naps: 9:30am and 2pm. Each nap is 1-1.5 hours."},
    ],
    "eczema": [
        {"title": "Allergies", "content": "Allergic to eggs and peanuts. Carries EpiPen. Dairy seems fine."},
        {"title": "Skin Care", "content": "Eczema on arms and cheeks. Apply Eucerin cream before sleep. Avoid fragranced products."},
        {"title": "Sleep Environment", "content": "Needs cooler room (19-20°C) due to eczema. Uses cotton-only bedding."},
        {"title": "Medication", "content": "Antihistamine (Zyrtec) if eczema flares up - makes her drowsy."},
    ],
}

SLEEP_SCHEDULES = {
    "newborn": {
        "bedtime": (19, 30),
        "wake_time": (6, 30),
        "naps": [
            ((9, 0), (10, 30)),
            ((12, 30), (14, 0)),
            ((15, 30), (16, 30)),
        ],
    },
    "infant": {
        "bedtime": (19, 0),
        "wake_time": (6, 0),
        "naps": [
            ((9, 30), (11, 0)),
            ((14, 0), (15, 30)),
        ],
    },
    "toddler": {
        "bedtime": (19, 30),
        "wake_time": (6, 30),
        "naps": [
            ((12, 30), (14, 30)),
        ],
    },
}

ALERT_TEMPLATES = {
    "temperature_high": {
        "type": "temperature",
        "title": "Room Too Warm",
        "message": "Temperature reached {value}°C in {baby_name}'s room. Optimal is 20-22°C.",
        "severity": "warning",
    },
    "temperature_low": {
        "type": "temperature",
        "title": "Room Too Cold",
        "message": "Temperature dropped to {value}°C in {baby_name}'s room. Consider warming the room.",
        "severity": "warning",
    },
    "humidity_high": {
        "type": "humidity",
        "title": "High Humidity",
        "message": "Humidity at {value}% in {baby_name}'s room. This may cause discomfort.",
        "severity": "info",
    },
    "humidity_low": {
        "type": "humidity",
        "title": "Low Humidity",
        "message": "Humidity dropped to {value}% in {baby_name}'s room. Consider using a humidifier.",
        "severity": "info",
    },
    "noise_high": {
        "type": "noise",
        "title": "Noise Detected",
        "message": "Noise level reached {value}dB in {baby_name}'s room.",
        "severity": "info",
    },
    "awakening": {
        "type": "awakening",
        "title": "{baby_name} Woke Up",
        "message": "{baby_name} woke up after {duration} of sleep.",
        "severity": "info",
    },
}

AI_INSIGHT_TEMPLATES = [
    "Temperature increased from {before}°C to {after}°C before awakening. Consider maintaining a cooler room temperature.",
    "Noise levels spiked to {value}dB around the time of awakening. Check for external noise sources.",
    "Humidity dropped significantly before awakening. The air might be too dry - consider a humidifier.",
    "Multiple environmental factors changed before awakening: temperature rose and noise increased slightly.",
    "Room conditions changed before awakening, possibly indicating discomfort from temperature shift.",
    "Sleep pattern disrupted earlier than usual. Environmental conditions were within normal range - may be developmental.",
]


def set_seed(seed: int):
    random.seed(seed)


def get_progress_factor(day_index: int) -> float:
    """Returns 0.0 (day 0) to 1.0 (day 89). Uses smoothstep: 3t^2 - 2t^3."""
    t = day_index / max(DAYS_OF_DATA - 1, 1)
    return t * t * (3.0 - 2.0 * t)


def lerp(start: float, end: float, t: float) -> float:
    return start + (end - start) * t


def get_awakening_count(age_category: str, progress: float) -> int:
    prog = AWAKENING_PROGRESSION[age_category]
    min_val = lerp(prog["start"][0], prog["end"][0], progress)
    max_val = lerp(prog["start"][1], prog["end"][1], progress)
    return max(0, round(random.uniform(min_val, max_val)))


def get_alert_read_status(alert_time: datetime) -> bool:
    days_ago = (NOW - alert_time).total_seconds() / 86400
    if days_ago > 30:
        return random.random() < ALERT_READ_OLD
    elif days_ago > 7:
        return random.random() < ALERT_READ_RECENT
    else:
        return random.random() < ALERT_READ_NEW


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def format_duration(minutes: float) -> str:
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins} minutes"


def get_night_cooling(hour: int) -> float:
    """Temp offset for hours 0-6; deepest cooling at 3-4am."""
    if 0 <= hour <= 6:
        depth = 1.0 - abs(hour - 3.5) / 3.5
        return lerp(NIGHT_COOLING_MAX, NIGHT_COOLING_MIN, depth)
    return 0.0


def generate_sensor_reading(
    progress: float,
    hour: int,
    weekend: bool,
) -> Dict[str, float]:
    base_temp = lerp(PROGRESSION["temp_start"], PROGRESSION["temp_end"], progress)
    base_humidity = lerp(PROGRESSION["humidity_start"], PROGRESSION["humidity_end"], progress)
    base_noise = lerp(PROGRESSION["noise_start"], PROGRESSION["noise_end"], progress)
    variance = lerp(PROGRESSION["variance_start"], PROGRESSION["variance_end"], progress)
    spike_chance = lerp(PROGRESSION["spike_chance_start"], PROGRESSION["spike_chance_end"], progress)

    if weekend:
        base_noise += WEEKEND_NOISE_BOOST
        base_temp += WEEKEND_TEMP_BOOST

    base_temp += get_night_cooling(hour)

    temp = base_temp + random.gauss(0, variance * 2)
    humidity = base_humidity + random.gauss(0, variance * 5)
    noise = base_noise + random.gauss(0, variance * 3)

    if random.random() < spike_chance:
        spike_type = random.choice(["temp", "humidity", "noise"])
        if spike_type == "temp":
            temp += random.uniform(2, 4)
        elif spike_type == "humidity":
            humidity += random.choice([-15, 15])
        else:
            noise += random.uniform(10, 20)

    temp = max(TEMP_MIN, min(TEMP_MAX, temp))
    humidity = max(HUMIDITY_MIN, min(HUMIDITY_MAX, humidity))
    noise = max(NOISE_MIN, min(NOISE_MAX, noise))

    return {
        "temp_celcius": round(temp, 1),
        "humidity": round(humidity, 1),
        "noise_decibel": round(noise, 1),
    }


def generate_correlation_parameters(
    all_readings: List[Dict[str, float]],
) -> Dict[str, Any]:
    """First 25% vs last 25% of readings, matching correlation_analyzer format."""
    if len(all_readings) < 4:
        return {}

    n = len(all_readings)
    q_size = max(1, int(n * CORRELATION_QUARTILE_FRACTION))
    first_quarter = all_readings[:q_size]
    last_quarter = all_readings[-q_size:]

    parameters = {}

    for key in ["temp_celcius", "humidity", "noise_decibel"]:
        start_avg = sum(r[key] for r in first_quarter) / len(first_quarter)
        end_avg = sum(r[key] for r in last_quarter) / len(last_quarter)

        if start_avg == 0:
            continue

        change_percent = ((end_avg - start_avg) / abs(start_avg)) * 100
        threshold = CORRELATION_CHANGE_THRESHOLDS.get(key, 5.0)

        if abs(change_percent) > threshold:
            parameters[key] = {
                "start_value": round(start_avg, 2),
                "end_value": round(end_avg, 2),
                "change_percent": round(change_percent, 2),
                "direction": "increase" if change_percent > 0 else "decrease",
            }

    return parameters


def generate_ai_insight(
    parameters: Dict[str, Any],
    baby_name: str,
) -> str:
    if not parameters:
        return f"{baby_name} woke up. Environmental conditions were stable - may be a developmental pattern or hunger."

    insights = []

    if "temp_celcius" in parameters:
        param = parameters["temp_celcius"]
        if param["direction"] == "increase":
            insights.append(f"Temperature rose from {param['start_value']}°C to {param['end_value']}°C")
        else:
            insights.append(f"Temperature dropped from {param['start_value']}°C to {param['end_value']}°C")

    if "noise_decibel" in parameters:
        param = parameters["noise_decibel"]
        insights.append(f"Noise level changed to {param['end_value']}dB")

    if "humidity" in parameters:
        param = parameters["humidity"]
        if param["direction"] == "decrease":
            insights.append("Humidity dropped - air may be too dry")
        else:
            insights.append("Humidity increased significantly")

    if insights:
        return f"{baby_name}: {'. '.join(insights)}. Consider adjusting room conditions."

    return random.choice(AI_INSIGHT_TEMPLATES)


def inject_sensor_drift(readings: List[Dict[str, float]]) -> None:
    """Mutate last N readings to create 8-15% drift crossing the 5% threshold. Modifies in-place."""
    if len(readings) < DRIFT_READINGS_COUNT + 2:
        return

    drift_param = random.choice(["temp_celcius", "humidity"])
    baseline_idx = len(readings) - DRIFT_READINGS_COUNT - 1
    baseline_value = readings[baseline_idx][drift_param]

    change_pct = random.uniform(0.08, 0.15)
    direction = random.choice([1, -1])
    target_value = baseline_value * (1 + change_pct * direction)

    if drift_param == "temp_celcius":
        target_value = max(TEMP_MIN, min(TEMP_MAX, target_value))
    else:
        target_value = max(HUMIDITY_MIN, min(HUMIDITY_MAX, target_value))

    drift_start = len(readings) - DRIFT_READINGS_COUNT
    for j in range(DRIFT_READINGS_COUNT):
        t = (j + 1) / DRIFT_READINGS_COUNT
        readings[drift_start + j][drift_param] = round(
            lerp(baseline_value, target_value, t), 1
        )


def _build_sleep_windows(
    day: date,
    age_category: str,
    weekend: bool,
) -> Tuple[List[Tuple[datetime, datetime]], List[Tuple[datetime, datetime]]]:
    """Returns (night_windows, nap_windows). Night: previous evening bedtime -> morning wake."""
    schedule = SLEEP_SCHEDULES[age_category]
    bedtime_h, bedtime_m = schedule["bedtime"]
    wake_h, wake_m = schedule["wake_time"]

    bed_shift = random.randint(WEEKEND_BEDTIME_SHIFT_MIN, WEEKEND_BEDTIME_SHIFT_MAX) if weekend else 0
    wake_shift = random.randint(WEEKEND_BEDTIME_SHIFT_MIN, WEEKEND_BEDTIME_SHIFT_MAX) if weekend else 0

    sleep_start = datetime.combine(
        day - timedelta(days=1),
        datetime.min.time().replace(hour=bedtime_h, minute=bedtime_m),
    ) + timedelta(minutes=bed_shift + random.randint(-10, 10))

    final_wake = datetime.combine(
        day,
        datetime.min.time().replace(hour=wake_h, minute=wake_m),
    ) + timedelta(minutes=wake_shift + random.randint(-10, 10))

    night_windows = [(sleep_start, final_wake)]

    nap_windows = []
    for nap_start_time, nap_end_time in schedule["naps"]:
        start_var = random.randint(-15, 15)
        end_var = random.randint(-15, 15)

        nap_start = datetime.combine(
            day,
            datetime.min.time().replace(hour=nap_start_time[0], minute=nap_start_time[1]),
        ) + timedelta(minutes=start_var)

        nap_end = datetime.combine(
            day,
            datetime.min.time().replace(hour=nap_end_time[0], minute=nap_end_time[1]),
        ) + timedelta(minutes=end_var)

        if random.random() < 0.15:
            continue

        nap_windows.append((nap_start, nap_end))

    return night_windows, nap_windows


def _generate_session_data(
    session_start: datetime,
    session_end: datetime,
    progress: float,
    weekend: bool,
    awakening_times: List[datetime],
    baby_name: str,
    inject_drifts: bool = True,
    is_ongoing: bool = False,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """If is_ongoing=True, last awakening_time = still sleeping; no awakening event created."""
    sensor_readings = []
    awakening_events = []
    alerts = []

    current_time = session_start
    seg_start = session_start
    readings_in_segment: List[Dict] = []

    for awk_idx, awake_time in enumerate(awakening_times):
        is_last = (awk_idx == len(awakening_times) - 1)
        skip_awakening = is_last and is_ongoing

        while current_time < awake_time:
            reading = generate_sensor_reading(
                progress=progress,
                hour=current_time.hour,
                weekend=weekend,
            )
            reading["datetime"] = current_time
            sensor_readings.append(reading)
            readings_in_segment.append(reading)

            if reading["temp_celcius"] > 24:
                alerts.append({
                    "type": "temperature",
                    "title": "Room Too Warm",
                    "message": f"Temperature reached {reading['temp_celcius']}°C in {baby_name}'s room.",
                    "severity": "warning",
                    "metadata": {"value": reading["temp_celcius"], "threshold": 24},
                    "created_at": current_time,
                })
            elif reading["temp_celcius"] < 18:
                alerts.append({
                    "type": "temperature",
                    "title": "Room Too Cold",
                    "message": f"Temperature dropped to {reading['temp_celcius']}°C in {baby_name}'s room.",
                    "severity": "warning",
                    "metadata": {"value": reading["temp_celcius"], "threshold": 18},
                    "created_at": current_time,
                })

            if reading["noise_decibel"] > 50:
                alerts.append({
                    "type": "noise",
                    "title": "Noise Detected",
                    "message": f"Noise level reached {reading['noise_decibel']}dB in {baby_name}'s room.",
                    "severity": "info",
                    "metadata": {"value": reading["noise_decibel"], "threshold": 50},
                    "created_at": current_time,
                })

            current_time += timedelta(minutes=SENSOR_INTERVAL_MINUTES)

        if skip_awakening:
            break

        if inject_drifts and random.random() < DRIFT_INJECTION_CHANCE and len(readings_in_segment) > DRIFT_READINGS_COUNT + 2:
            inject_sensor_drift(readings_in_segment)

        sleep_duration = (awake_time - seg_start).total_seconds() / 60
        correlation_params = generate_correlation_parameters(readings_in_segment)
        ai_insight = generate_ai_insight(correlation_params, baby_name)
        last_reading = readings_in_segment[-1] if readings_in_segment else None

        awakening_event = {
            "sleep_started_at": seg_start.isoformat(),
            "awakened_at": awake_time.isoformat(),
            "sleep_duration_minutes": round(sleep_duration, 1),
            "ai_insight": ai_insight,
            "last_sensor_readings": {
                "temp_celcius": last_reading["temp_celcius"],
                "humidity": last_reading["humidity"],
                "noise_decibel": last_reading["noise_decibel"],
            } if last_reading else None,
            "correlation_params": correlation_params,
        }
        awakening_events.append(awakening_event)

        alerts.append({
            "type": "awakening",
            "title": f"{baby_name} Woke Up",
            "message": f"{baby_name} woke up after {format_duration(sleep_duration)} of sleep.",
            "severity": "info",
            "metadata": {
                "sleep_duration_minutes": sleep_duration,
                "sleep_started_at": seg_start.isoformat(),
            },
            "created_at": awake_time,
        })

        seg_start = awake_time + timedelta(minutes=random.randint(5, 20))
        current_time = seg_start
        readings_in_segment = []

    return sensor_readings, awakening_events, alerts


def generate_day_data(
    baby_data: Dict,
    day: date,
    day_index: int,
    is_today: bool = False,
    force_currently_sleeping: bool = False,
) -> Tuple[List[Dict], List[Dict], List[Dict], bool]:
    age_category = baby_data["age_category"]
    progress = get_progress_factor(day_index)
    weekend = is_weekend(day)
    baby_name = baby_data["first_name"]

    night_windows, nap_windows = _build_sleep_windows(day, age_category, weekend)

    all_readings = []
    all_awakenings = []
    all_alerts = []
    baby_is_sleeping = False

    for sleep_start, final_wake in night_windows:
        effective_end = min(final_wake, NOW) if is_today else final_wake
        if sleep_start >= effective_end:
            continue

        num_awakenings = get_awakening_count(age_category, progress)
        awakening_times = []

        if num_awakenings > 0:
            night_duration = (effective_end - sleep_start).total_seconds() / 60
            segment_duration = night_duration / (num_awakenings + 1)
            for i in range(num_awakenings):
                awake_offset = segment_duration * (i + 1) + random.randint(-30, 30)
                awake_time = sleep_start + timedelta(minutes=max(10, awake_offset))
                if awake_time < effective_end:
                    awakening_times.append(awake_time)

        is_ongoing = False
        if is_today and sleep_start <= NOW <= final_wake:
            is_ongoing = True
            baby_is_sleeping = True
            awakening_times.append(NOW)
        elif is_today and NOW < final_wake:
            awakening_times = [t for t in awakening_times if t <= NOW]
        else:
            awakening_times.append(effective_end)

        if not awakening_times:
            awakening_times.append(effective_end)

        readings, awakenings, alerts = _generate_session_data(
            session_start=sleep_start,
            session_end=effective_end,
            progress=progress,
            weekend=weekend,
            awakening_times=awakening_times,
            baby_name=baby_name,
            inject_drifts=True,
            is_ongoing=is_ongoing,
        )
        all_readings.extend(readings)
        all_awakenings.extend(awakenings)
        all_alerts.extend(alerts)

    for nap_start, nap_end in nap_windows:
        if is_today:
            if nap_start > NOW:
                if force_currently_sleeping and not baby_is_sleeping:
                    nap_start = NOW - timedelta(minutes=random.randint(10, 20))
                    nap_end = nap_start + timedelta(minutes=60)
                else:
                    continue

            effective_nap_end = min(nap_end, NOW)

            is_nap_ongoing = (nap_start <= NOW <= nap_end)
            if is_nap_ongoing:
                baby_is_sleeping = True

            if nap_start >= effective_nap_end and not is_nap_ongoing:
                continue

            awakening_times = []
            if is_nap_ongoing:
                awakening_times = [NOW]
            else:
                awakening_times = [effective_nap_end]

            readings, awakenings, alerts = _generate_session_data(
                session_start=nap_start,
                session_end=effective_nap_end if not is_nap_ongoing else NOW,
                progress=progress,
                weekend=weekend,
                awakening_times=awakening_times,
                baby_name=baby_name,
                inject_drifts=False,
                is_ongoing=is_nap_ongoing,
            )
            all_readings.extend(readings)
            all_awakenings.extend(awakenings)
            all_alerts.extend(alerts)
        else:
            readings, awakenings, alerts = _generate_session_data(
                session_start=nap_start,
                session_end=nap_end,
                progress=progress,
                weekend=weekend,
                awakening_times=[nap_end],
                baby_name=baby_name,
                inject_drifts=False,
                is_ongoing=False,
            )
            all_readings.extend(readings)
            all_awakenings.extend(awakenings)
            all_alerts.extend(alerts)

    if is_today and force_currently_sleeping and not baby_is_sleeping:
        fake_start = NOW - timedelta(minutes=random.randint(10, 20))
        reading_time = fake_start
        readings_list = []
        while reading_time < NOW:
            reading = generate_sensor_reading(progress=progress, hour=reading_time.hour, weekend=weekend)
            reading["datetime"] = reading_time
            readings_list.append(reading)
            reading_time += timedelta(minutes=SENSOR_INTERVAL_MINUTES)

        all_readings.extend(readings_list)
        baby_is_sleeping = True

    return all_readings, all_awakenings, all_alerts, baby_is_sleeping


async def truncate_tables(session):
    tables = [
        "push_subscriptions",
        "alerts",
        "optimal_stats",
        "daily_summary",
        "correlations",
        "awakening_events",
        "sleep_realtime_data",
        "baby_notes",
        "users",
        "babies",
    ]

    print("Truncating tables...")
    for table in tables:
        try:
            await session.execute(text(f'TRUNCATE TABLE "Nappi"."{table}" CASCADE'))
            print(f"  - Truncated {table}")
        except Exception as e:
            print(f"  - Warning: Could not truncate {table}: {e}")

    await session.commit()
    print("Tables truncated.\n")


async def seed_babies(session) -> List[int]:
    print("Seeding babies...")
    baby_ids = []

    for baby in BABIES_DATA:
        result = await session.execute(
            text('''
                INSERT INTO "Nappi"."babies" (first_name, last_name, birthdate, gender, created_at)
                VALUES (:first_name, :last_name, :birthdate, :gender, NOW())
                RETURNING id
            '''),
            {
                "first_name": baby["first_name"],
                "last_name": baby["last_name"],
                "birthdate": baby["birthdate"],
                "gender": baby["gender"],
            }
        )
        baby_id = result.scalar()
        baby_ids.append(baby_id)
        print(f"  - Created baby: {baby['first_name']} {baby['last_name']} (ID: {baby_id})")

    await session.commit()
    return baby_ids


async def seed_users(session, baby_ids: List[int]) -> List[int]:
    print("Seeding users...")
    user_ids = []

    for user in USERS_DATA:
        baby_id = baby_ids[user["baby_index"]]
        result = await session.execute(
            text('''
                INSERT INTO "Nappi"."users" (username, password, first_name, last_name, baby_id)
                VALUES (:username, :password, :first_name, :last_name, :baby_id)
                RETURNING id
            '''),
            {
                "username": user["username"],
                "password": user["password"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "baby_id": baby_id,
            }
        )
        user_id = result.scalar()
        user_ids.append(user_id)
        print(f"  - Created user: {user['username']} (ID: {user_id}, baby_id: {baby_id})")

    await session.commit()
    return user_ids


async def seed_baby_notes(session, baby_ids: List[int]):
    print("Seeding baby notes...")

    for i, baby_id in enumerate(baby_ids):
        baby = BABIES_DATA[i]
        notes = BABY_NOTES_DATA.get(baby["notes_theme"], [])

        for note in notes:
            days_ago = random.randint(1, 30)
            created_at = NOW - timedelta(days=days_ago)

            await session.execute(
                text('''
                    INSERT INTO "Nappi"."baby_notes" (baby_id, title, content, created_at, updated_at)
                    VALUES (:baby_id, :title, :content, :created_at, :updated_at)
                '''),
                {
                    "baby_id": baby_id,
                    "title": note["title"],
                    "content": note["content"],
                    "created_at": created_at,
                    "updated_at": created_at,
                }
            )

        print(f"  - Created {len(notes)} notes for baby {baby['first_name']}")

    await session.commit()


async def seed_sleep_realtime_data(
    session,
    baby_ids: List[int],
    user_ids: List[int],
):
    print(f"\nSeeding {DAYS_OF_DATA} days of sleep data (ending at {NOW.strftime('%Y-%m-%d %H:%M')})...")

    all_sensor_data = {baby_id: [] for baby_id in baby_ids}
    all_awakenings = {baby_id: [] for baby_id in baby_ids}
    currently_sleeping = {}

    for i, baby_id in enumerate(baby_ids):
        baby_data = BABIES_DATA[i]
        user_id = user_ids[i]
        is_demo_baby = (i == 0)

        print(f"\n  Generating data for {baby_data['first_name']}...")

        baby_alerts = []

        for day_index in range(DAYS_OF_DATA):
            day = (NOW - timedelta(days=DAYS_OF_DATA - 1 - day_index)).date()
            is_today = (day == NOW.date())

            sensor_readings, awakenings, alerts, baby_sleeping = generate_day_data(
                baby_data=baby_data,
                day=day,
                day_index=day_index,
                is_today=is_today,
                force_currently_sleeping=(is_today and is_demo_baby),
            )

            all_sensor_data[baby_id].extend(sensor_readings)
            all_awakenings[baby_id].extend(awakenings)
            baby_alerts.extend(alerts)

            if is_today and baby_sleeping:
                currently_sleeping[baby_id] = True

            if (day_index + 1) % 30 == 0:
                print(f"    - Processed {day_index + 1}/{DAYS_OF_DATA} days")

        sensor_data = all_sensor_data[baby_id]
        print(f"    - Inserting {len(sensor_data)} sensor readings...")
        for batch_start in range(0, len(sensor_data), BATCH_SIZE):
            batch = sensor_data[batch_start:batch_start + BATCH_SIZE]
            if batch:
                values_list = []
                params = {"baby_id": baby_id}
                for idx, reading in enumerate(batch):
                    values_list.append(f"(:baby_id, :dt{idx}, :hum{idx}, :temp{idx}, :noise{idx})")
                    params[f"dt{idx}"] = reading["datetime"]
                    params[f"hum{idx}"] = reading["humidity"]
                    params[f"temp{idx}"] = reading["temp_celcius"]
                    params[f"noise{idx}"] = reading["noise_decibel"]

                values_sql = ", ".join(values_list)
                await session.execute(
                    text(f'''
                        INSERT INTO "Nappi"."sleep_realtime_data"
                        (baby_id, datetime, humidity, temp_celcius, noise_decibel)
                        VALUES {values_sql}
                    '''),
                    params
                )
            if batch_start % 5000 == 0 and batch_start > 0:
                print(f"      - Inserted {batch_start}/{len(sensor_data)} readings...")
                await session.commit()

        print(f"    - Inserting {len(all_awakenings[baby_id])} awakening events...")
        for event in all_awakenings[baby_id]:
            correlation_params = event.pop("correlation_params", {})

            result = await session.execute(
                text('''
                    INSERT INTO "Nappi"."awakening_events" (baby_id, event_metadata)
                    VALUES (:baby_id, CAST(:event_metadata AS jsonb))
                    RETURNING id
                '''),
                {
                    "baby_id": baby_id,
                    "event_metadata": json.dumps(event),
                }
            )
            event_id = result.scalar()

            if correlation_params:
                awakened_at = datetime.fromisoformat(event["awakened_at"])
                await session.execute(
                    text('''
                        INSERT INTO "Nappi"."correlations" (baby_id, time, parameters, extra_data)
                        VALUES (:baby_id, :time, CAST(:parameters AS jsonb), :extra_data)
                    '''),
                    {
                        "baby_id": baby_id,
                        "time": awakened_at.date(),
                        "parameters": json.dumps(correlation_params),
                        "extra_data": event.get("ai_insight", ""),
                    }
                )

        print(f"    - Inserting {len(baby_alerts)} alerts...")
        for batch_start in range(0, len(baby_alerts), 50):
            batch = baby_alerts[batch_start:batch_start + 50]
            if batch:
                values_list = []
                params = {"baby_id": baby_id, "user_id": user_id}
                for idx, alert in enumerate(batch):
                    values_list.append(
                        f"(:baby_id, :user_id, :type{idx}, :title{idx}, :msg{idx}, "
                        f":sev{idx}, CAST(:meta{idx} AS jsonb), :read{idx}, :cat{idx})"
                    )
                    params[f"type{idx}"] = alert["type"]
                    params[f"title{idx}"] = alert["title"]
                    params[f"msg{idx}"] = alert["message"]
                    params[f"sev{idx}"] = alert["severity"]
                    params[f"meta{idx}"] = json.dumps(alert.get("metadata", {}))
                    params[f"read{idx}"] = get_alert_read_status(alert["created_at"])
                    params[f"cat{idx}"] = alert["created_at"]

                values_sql = ", ".join(values_list)
                await session.execute(
                    text(f'''
                        INSERT INTO "Nappi"."alerts"
                        (baby_id, user_id, type, title, message, severity, metadata, read, created_at)
                        VALUES {values_sql}
                    '''),
                    params
                )

        await session.commit()

    return all_sensor_data, all_awakenings, currently_sleeping


async def seed_daily_summaries(
    session,
    baby_ids: List[int],
    all_sensor_data: Dict[int, List[Dict]],
    all_awakenings: Dict[int, List[Dict]],
):
    print("\nSeeding daily summaries...")

    for i, baby_id in enumerate(baby_ids):
        baby_data = BABIES_DATA[i]
        sensor_data = all_sensor_data[baby_id]
        awakenings = all_awakenings[baby_id]

        data_by_date: Dict[date, List[Dict]] = {}
        for reading in sensor_data:
            reading_date = reading["datetime"].date()
            if reading_date not in data_by_date:
                data_by_date[reading_date] = []
            data_by_date[reading_date].append(reading)

        awakenings_by_date: Dict[date, List[Dict]] = {}
        for event in awakenings:
            awakened_at = datetime.fromisoformat(event["awakened_at"])
            event_date = awakened_at.date()
            if event_date not in awakenings_by_date:
                awakenings_by_date[event_date] = []
            awakenings_by_date[event_date].append(event)

        summaries_created = 0
        prev_avg_temp = 21.0
        prev_avg_humidity = 50.0
        prev_avg_noise = 35.0

        for day_index in range(DAYS_OF_DATA):
            summary_date = (NOW - timedelta(days=DAYS_OF_DATA - 1 - day_index)).date()
            readings = data_by_date.get(summary_date, [])

            if readings:
                avg_temp = sum(r["temp_celcius"] for r in readings) / len(readings)
                avg_humidity = sum(r["humidity"] for r in readings) / len(readings)
                avg_noise = sum(r["noise_decibel"] for r in readings) / len(readings)
                prev_avg_temp = avg_temp
                prev_avg_humidity = avg_humidity
                prev_avg_noise = avg_noise
            else:
                avg_temp = prev_avg_temp
                avg_humidity = prev_avg_humidity
                avg_noise = prev_avg_noise

            day_awakenings = awakenings_by_date.get(summary_date, [])
            morning_awakes = 0
            noon_awakes = 0
            night_awakes = 0

            for event in day_awakenings:
                awakened_at = datetime.fromisoformat(event["awakened_at"])
                hour = awakened_at.hour
                if 6 <= hour < 12:
                    morning_awakes += 1
                elif 12 <= hour < 18:
                    noon_awakes += 1
                else:
                    night_awakes += 1

            await session.execute(
                text('''
                    INSERT INTO "Nappi"."daily_summary"
                    (baby_id, summary_date, avg_temp, avg_humidity, avg_noise,
                     morning_awakes_sum, noon_awakes_sum, night_awakes_sum)
                    VALUES (:baby_id, :summary_date, :avg_temp, :avg_humidity, :avg_noise,
                            :morning_awakes_sum, :noon_awakes_sum, :night_awakes_sum)
                '''),
                {
                    "baby_id": baby_id,
                    "summary_date": summary_date,
                    "avg_temp": round(avg_temp, 1),
                    "avg_humidity": round(avg_humidity, 1),
                    "avg_noise": round(avg_noise, 1),
                    "morning_awakes_sum": morning_awakes,
                    "noon_awakes_sum": noon_awakes,
                    "night_awakes_sum": night_awakes,
                }
            )
            summaries_created += 1

        print(f"  - Created {summaries_created} daily summaries for {baby_data['first_name']}")

    await session.commit()


async def seed_optimal_stats(
    session,
    baby_ids: List[int],
    all_sensor_data: Dict[int, List[Dict]],
    all_awakenings: Dict[int, List[Dict]],
):
    """Weight = 1/(OPTIMAL_STATS_WEIGHT_BASE + awakenings). Optimal = sum(value*weight)/sum(weight)."""
    print("\nSeeding optimal stats...")

    for i, baby_id in enumerate(baby_ids):
        baby_data = BABIES_DATA[i]
        sensor_data = all_sensor_data[baby_id]
        awakenings = all_awakenings[baby_id]

        if not sensor_data:
            continue

        data_by_date: Dict[date, List[Dict]] = {}
        for reading in sensor_data:
            reading_date = reading["datetime"].date()
            if reading_date not in data_by_date:
                data_by_date[reading_date] = []
            data_by_date[reading_date].append(reading)

        awakenings_per_date: Dict[date, int] = {}
        for event in awakenings:
            awakened_at = datetime.fromisoformat(event["awakened_at"])
            event_date = awakened_at.date()
            awakenings_per_date[event_date] = awakenings_per_date.get(event_date, 0) + 1

        weighted_temp = 0.0
        weighted_humidity = 0.0
        weighted_noise = 0.0
        total_weight = 0.0

        for d, readings in data_by_date.items():
            total_awk = awakenings_per_date.get(d, 0)
            weight = 1.0 / (OPTIMAL_STATS_WEIGHT_BASE + total_awk)

            day_avg_temp = sum(r["temp_celcius"] for r in readings) / len(readings)
            day_avg_humidity = sum(r["humidity"] for r in readings) / len(readings)
            day_avg_noise = sum(r["noise_decibel"] for r in readings) / len(readings)

            weighted_temp += day_avg_temp * weight
            weighted_humidity += day_avg_humidity * weight
            weighted_noise += day_avg_noise * weight
            total_weight += weight

        if total_weight > 0:
            optimal_temp = weighted_temp / total_weight
            optimal_humidity = weighted_humidity / total_weight
            optimal_noise = weighted_noise / total_weight
        else:
            optimal_temp = 21.0
            optimal_humidity = 50.0
            optimal_noise = 35.0

        await session.execute(
            text('''
                INSERT INTO "Nappi"."optimal_stats"
                (baby_id, temperature, humidity, noise)
                VALUES (:baby_id, :temperature, :humidity, :noise)
            '''),
            {
                "baby_id": baby_id,
                "temperature": round(optimal_temp, 1),
                "humidity": round(optimal_humidity, 1),
                "noise": round(optimal_noise, 1),
            }
        )

        print(f"  - Created optimal stats for {baby_data['first_name']}: "
              f"temp={round(optimal_temp, 1)}°C, humidity={round(optimal_humidity, 1)}%, "
              f"noise={round(optimal_noise, 1)}dB")

    await session.commit()


async def print_validation_summary(session, currently_sleeping: Dict[int, bool]):
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    start_date = (NOW - timedelta(days=DAYS_OF_DATA - 1)).date()
    print(f"  Date range: {start_date} -> {NOW.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Progress: day 1 (oldest) -> day {DAYS_OF_DATA} (now)")
    print()

    tables = [
        ("babies", "baby profiles"),
        ("users", "user accounts"),
        ("baby_notes", "baby notes"),
        ("sleep_realtime_data", "sensor readings"),
        ("awakening_events", "awakening events"),
        ("correlations", "correlation records"),
        ("daily_summary", "daily summaries"),
        ("optimal_stats", "optimal stats"),
        ("alerts", "alerts"),
    ]

    for table, description in tables:
        result = await session.execute(text(f'SELECT COUNT(*) FROM "Nappi"."{table}"'))
        count = result.scalar()
        print(f"  {description:.<30} {count:>8}")

    print()
    for baby_id, sleeping in currently_sleeping.items():
        if sleeping:
            print(f"  Baby ID {baby_id} is CURRENTLY SLEEPING (live dashboard active)")

    print()
    result = await session.execute(text('''
        SELECT summary_date, avg_temp, avg_humidity, avg_noise
        FROM "Nappi"."daily_summary"
        WHERE baby_id = (SELECT MIN(id) FROM "Nappi"."babies")
        ORDER BY summary_date ASC
        LIMIT 1
    '''))
    first = result.fetchone()
    result = await session.execute(text('''
        SELECT summary_date, avg_temp, avg_humidity, avg_noise
        FROM "Nappi"."daily_summary"
        WHERE baby_id = (SELECT MIN(id) FROM "Nappi"."babies")
        ORDER BY summary_date DESC
        LIMIT 1
    '''))
    last = result.fetchone()

    if first and last:
        print(f"  Progression (Emma, demo baby):")
        print(f"    Day 1  ({first[0]}): temp={first[1]}°C, humidity={first[2]}%, noise={first[3]}dB")
        print(f"    Day 90 ({last[0]}): temp={last[1]}°C, humidity={last[2]}%, noise={last[3]}dB")

    print("\n" + "-" * 60)
    print("Demo Login Credentials:")
    print("-" * 60)
    print("  Username: demo@nappi.app")
    print("  Password: demo123")
    print("=" * 60)


async def seed_database():
    print("\n" + "=" * 60)
    print("NAPPI DEMO DATA SEEDER")
    print("=" * 60)
    print(f"WARNING: This will DELETE all existing data!")
    print(f"Generating {DAYS_OF_DATA} days of progressive data for {len(BABIES_DATA)} babies...")
    print(f"Time anchor: {NOW.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Demo baby (Emma) will be currently sleeping at script time.")
    print("=" * 60 + "\n")

    set_seed(SEED)

    db = get_database()
    await db.connect(settings.DATABASE_URL)

    try:
        async with db.session() as session:
            await truncate_tables(session)
            baby_ids = await seed_babies(session)
            user_ids = await seed_users(session, baby_ids)
            await seed_baby_notes(session, baby_ids)
            all_sensor_data, all_awakenings, currently_sleeping = await seed_sleep_realtime_data(
                session, baby_ids, user_ids
            )
            await seed_daily_summaries(
                session, baby_ids, all_sensor_data, all_awakenings
            )
            await seed_optimal_stats(
                session, baby_ids, all_sensor_data, all_awakenings
            )
            await print_validation_summary(session, currently_sleeping)

        print("\nSeeding completed successfully!")

    except Exception as e:
        print(f"\nError during seeding: {e}")
        raise
    finally:
        await db.disconnect()


def main():
    asyncio.run(seed_database())


if __name__ == "__main__":
    main()
