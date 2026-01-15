"""
Demo Data Seeder for Nappi

Populates the database with realistic mock data for demonstration purposes.
WARNING: This script will DELETE all existing data!

Usage:
    cd backend
    python -m app.db.seed_demo_data
"""

import asyncio
import json
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Tuple, Optional

from sqlalchemy import text

from app.core.database import get_database
from app.core.settings import settings


# =============================================================================
# Configuration
# =============================================================================

SEED = 42  # For reproducible random data
DAYS_OF_DATA = 90  # How many days of historical data to generate
SENSOR_INTERVAL_MINUTES = 5  # How often sensor readings are recorded during sleep
BATCH_SIZE = 500  # Number of rows to insert in a single batch (for performance)

# Realistic sensor ranges
TEMP_OPTIMAL = 21.0
TEMP_MIN, TEMP_MAX = 18.0, 26.0
HUMIDITY_OPTIMAL = 50.0
HUMIDITY_MIN, HUMIDITY_MAX = 35.0, 70.0
NOISE_OPTIMAL = 35.0
NOISE_MIN, NOISE_MAX = 25.0, 55.0

# Heart rate by age (bpm)
HEART_RATE_RANGES = {
    "newborn": (100, 160),    # 0-3 months
    "infant": (90, 150),      # 4-12 months
    "toddler": (80, 130),     # 12+ months
}


# =============================================================================
# Demo Data Definitions
# =============================================================================

BABIES_DATA = [
    {
        "first_name": "Emma",
        "last_name": "Cohen",
        "birthdate": date.today() - timedelta(days=90),  # 3 months old
        "gender": "female",
        "age_category": "newborn",
        "notes_theme": "newborn_reflux",
    },
    {
        "first_name": "Noah",
        "last_name": "Levy",
        "birthdate": date.today() - timedelta(days=210),  # 7 months old
        "gender": "male",
        "age_category": "infant",
        "notes_theme": "teething",
    },
    {
        "first_name": "Mia",
        "last_name": "Ben-David",
        "birthdate": date.today() - timedelta(days=420),  # 14 months old
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
        "baby_index": 0,  # Emma Cohen
    },
    {
        "username": "david@nappi.app",
        "password": "david123",
        "first_name": "David",
        "last_name": "Levy",
        "baby_index": 1,  # Noah Levy
    },
    {
        "username": "maya@nappi.app",
        "password": "maya123",
        "first_name": "Maya",
        "last_name": "Ben-David",
        "baby_index": 2,  # Mia Ben-David
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

# Sleep schedules by age category
SLEEP_SCHEDULES = {
    "newborn": {
        "bedtime": (19, 30),  # 7:30 PM
        "wake_time": (6, 30),  # 6:30 AM
        "naps": [
            ((9, 0), (10, 30)),    # Morning nap
            ((12, 30), (14, 0)),   # Early afternoon
            ((15, 30), (16, 30)),  # Late afternoon
        ],
        "awakenings_per_night": (2, 4),  # More frequent for newborns
    },
    "infant": {
        "bedtime": (19, 0),  # 7 PM
        "wake_time": (6, 0),  # 6 AM
        "naps": [
            ((9, 30), (11, 0)),   # Morning nap
            ((14, 0), (15, 30)),  # Afternoon nap
        ],
        "awakenings_per_night": (1, 3),
    },
    "toddler": {
        "bedtime": (19, 30),  # 7:30 PM
        "wake_time": (6, 30),  # 6:30 AM
        "naps": [
            ((12, 30), (14, 30)),  # Single afternoon nap
        ],
        "awakenings_per_night": (0, 2),  # Fewer awakenings
    },
}

# Alert templates
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

# AI insight templates for correlations
AI_INSIGHT_TEMPLATES = [
    "Temperature increased from {before}°C to {after}°C before awakening. Consider maintaining a cooler room temperature.",
    "Noise levels spiked to {value}dB around the time of awakening. Check for external noise sources.",
    "Humidity dropped significantly before awakening. The air might be too dry - consider a humidifier.",
    "Multiple environmental factors changed before awakening: temperature rose and noise increased slightly.",
    "Heart rate elevated before awakening, possibly indicating discomfort from room temperature.",
    "Sleep pattern disrupted earlier than usual. Environmental conditions were within normal range - may be developmental.",
]


# =============================================================================
# Helper Functions
# =============================================================================

def set_seed(seed: int):
    """Set random seed for reproducibility."""
    random.seed(seed)


def generate_sensor_reading(
    base_temp: float = TEMP_OPTIMAL,
    base_humidity: float = HUMIDITY_OPTIMAL,
    base_noise: float = NOISE_OPTIMAL,
    heart_rate_range: Tuple[int, int] = (90, 140),
    variance: float = 0.3,
    spike_chance: float = 0.05,
) -> Dict[str, float]:
    """Generate realistic sensor readings with occasional spikes."""
    
    # Normal variance
    temp = base_temp + random.gauss(0, variance * 2)
    humidity = base_humidity + random.gauss(0, variance * 5)
    noise = base_noise + random.gauss(0, variance * 3)
    heart_rate = random.uniform(*heart_rate_range)
    
    # Occasional spikes (these often cause awakenings)
    if random.random() < spike_chance:
        spike_type = random.choice(["temp", "humidity", "noise"])
        if spike_type == "temp":
            temp += random.uniform(2, 4)  # Temperature spike
        elif spike_type == "humidity":
            humidity += random.choice([-15, 15])  # Humidity change
        else:
            noise += random.uniform(10, 20)  # Noise spike
    
    # Clamp to realistic ranges
    temp = max(TEMP_MIN, min(TEMP_MAX, temp))
    humidity = max(HUMIDITY_MIN, min(HUMIDITY_MAX, humidity))
    noise = max(NOISE_MIN, min(NOISE_MAX, noise))
    
    return {
        "temp_celcius": round(temp, 1),
        "humidity": round(humidity, 1),
        "noise_decibel": round(noise, 1),
        "heart_rate": round(heart_rate, 0),
    }


def generate_sleep_quality_score(
    temp: float,
    humidity: float,
    noise: float,
) -> int:
    """Calculate sleep quality score (0-100) based on environmental factors."""
    score = 100
    
    # Temperature penalty
    temp_diff = abs(temp - TEMP_OPTIMAL)
    score -= min(20, temp_diff * 5)
    
    # Humidity penalty
    humidity_diff = abs(humidity - HUMIDITY_OPTIMAL)
    score -= min(15, humidity_diff * 0.5)
    
    # Noise penalty
    noise_diff = max(0, noise - NOISE_OPTIMAL)
    score -= min(25, noise_diff * 1.5)
    
    return max(0, min(100, int(score)))


def generate_correlation_parameters(
    before_readings: Dict[str, float],
    after_readings: Dict[str, float],
) -> Dict[str, Any]:
    """Generate correlation parameters showing what changed before awakening."""
    parameters = {}
    
    for key in ["temp_celcius", "humidity", "noise_decibel"]:
        before = before_readings.get(key, 0)
        after = after_readings.get(key, 0)
        
        if before > 0:
            change_percent = ((after - before) / before) * 100
            
            # Only include if change is significant (>5%)
            if abs(change_percent) > 5:
                parameters[key] = {
                    "before": before,
                    "after": after,
                    "change_percent": round(change_percent, 1),
                    "direction": "increased" if change_percent > 0 else "decreased",
                }
    
    return parameters


def generate_ai_insight(
    parameters: Dict[str, Any],
    baby_name: str,
) -> str:
    """Generate an AI insight based on correlation parameters."""
    if not parameters:
        return f"{baby_name} woke up. Environmental conditions were stable - may be a developmental pattern or hunger."
    
    insights = []
    
    if "temp_celcius" in parameters:
        param = parameters["temp_celcius"]
        if param["direction"] == "increased":
            insights.append(f"Temperature rose from {param['before']}°C to {param['after']}°C")
        else:
            insights.append(f"Temperature dropped from {param['before']}°C to {param['after']}°C")
    
    if "noise_decibel" in parameters:
        param = parameters["noise_decibel"]
        insights.append(f"Noise level changed to {param['after']}dB")
    
    if "humidity" in parameters:
        param = parameters["humidity"]
        if param["direction"] == "decreased":
            insights.append("Humidity dropped - air may be too dry")
        else:
            insights.append("Humidity increased significantly")
    
    if insights:
        return f"{baby_name}: {'. '.join(insights)}. Consider adjusting room conditions."
    
    return random.choice(AI_INSIGHT_TEMPLATES)


def format_duration(minutes: float) -> str:
    """Format duration in minutes to human-readable string."""
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins} minutes"


# =============================================================================
# Data Generation Functions
# =============================================================================

async def truncate_tables(session):
    """Truncate all tables in reverse dependency order."""
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
    """Seed babies table and return list of baby IDs."""
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
    """Seed users table linked to babies."""
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
    """Seed baby_notes table with multiple notes per baby."""
    print("Seeding baby notes...")
    
    for i, baby_id in enumerate(baby_ids):
        baby = BABIES_DATA[i]
        notes = BABY_NOTES_DATA.get(baby["notes_theme"], [])
        
        for note in notes:
            # Randomize created_at within the past 30 days
            days_ago = random.randint(1, 30)
            created_at = datetime.now() - timedelta(days=days_ago)
            
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


async def seed_sleep_data_for_day(
    session,
    baby_id: int,
    baby_data: Dict,
    day: date,
    user_id: int,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Generate sleep data for a single day.
    Returns: (sensor_readings, awakening_events, alerts)
    """
    age_category = baby_data["age_category"]
    schedule = SLEEP_SCHEDULES[age_category]
    hr_range = HEART_RATE_RANGES[age_category]
    
    sensor_readings = []
    awakening_events = []
    alerts = []
    
    # Generate night sleep (previous evening to morning)
    bedtime_hour, bedtime_min = schedule["bedtime"]
    wake_hour, wake_min = schedule["wake_time"]
    
    # Night sleep starts previous day evening
    sleep_start = datetime.combine(day - timedelta(days=1), datetime.min.time().replace(
        hour=bedtime_hour, minute=bedtime_min
    ))
    final_wake = datetime.combine(day, datetime.min.time().replace(
        hour=wake_hour, minute=wake_min
    ))
    
    # Generate night awakenings
    num_awakenings = random.randint(*schedule["awakenings_per_night"])
    awakening_times = []
    
    if num_awakenings > 0:
        # Distribute awakenings throughout the night
        night_duration = (final_wake - sleep_start).total_seconds() / 60
        segment_duration = night_duration / (num_awakenings + 1)
        
        for i in range(num_awakenings):
            awake_offset = segment_duration * (i + 1) + random.randint(-30, 30)
            awake_time = sleep_start + timedelta(minutes=awake_offset)
            awakening_times.append(awake_time)
    
    # Add final morning wake
    awakening_times.append(final_wake)
    
    # Generate sensor data and awakenings for night sleep
    current_time = sleep_start
    session_start = sleep_start
    base_temp = TEMP_OPTIMAL + random.uniform(-1, 1)
    base_humidity = HUMIDITY_OPTIMAL + random.uniform(-5, 5)
    base_noise = NOISE_OPTIMAL + random.uniform(-3, 3)
    
    readings_before_awakening = []
    
    for awake_time in awakening_times:
        # Generate readings until awakening
        while current_time < awake_time:
            # Gradually drift conditions and occasionally spike near awakenings
            time_to_awakening = (awake_time - current_time).total_seconds() / 60
            spike_chance = 0.15 if time_to_awakening < 30 else 0.03
            
            reading = generate_sensor_reading(
                base_temp, base_humidity, base_noise,
                hr_range, spike_chance=spike_chance
            )
            reading["datetime"] = current_time
            reading["sleep_quality_score"] = generate_sleep_quality_score(
                reading["temp_celcius"],
                reading["humidity"],
                reading["noise_decibel"],
            )
            sensor_readings.append(reading)
            readings_before_awakening.append(reading)
            
            # Check for alert conditions
            if reading["temp_celcius"] > 24:
                alerts.append({
                    "type": "temperature",
                    "title": "Room Too Warm",
                    "message": f"Temperature reached {reading['temp_celcius']}°C in {baby_data['first_name']}'s room.",
                    "severity": "warning",
                    "metadata": {"value": reading["temp_celcius"], "threshold": 24},
                    "created_at": current_time,
                })
            elif reading["temp_celcius"] < 18:
                alerts.append({
                    "type": "temperature",
                    "title": "Room Too Cold",
                    "message": f"Temperature dropped to {reading['temp_celcius']}°C in {baby_data['first_name']}'s room.",
                    "severity": "warning",
                    "metadata": {"value": reading["temp_celcius"], "threshold": 18},
                    "created_at": current_time,
                })
            
            if reading["noise_decibel"] > 50:
                alerts.append({
                    "type": "noise",
                    "title": "Noise Detected",
                    "message": f"Noise level reached {reading['noise_decibel']}dB in {baby_data['first_name']}'s room.",
                    "severity": "info",
                    "metadata": {"value": reading["noise_decibel"], "threshold": 50},
                    "created_at": current_time,
                })
            
            current_time += timedelta(minutes=SENSOR_INTERVAL_MINUTES)
        
        # Record awakening event
        sleep_duration = (awake_time - session_start).total_seconds() / 60
        
        # Get readings for correlation (before and at awakening)
        if len(readings_before_awakening) >= 2:
            before_reading = readings_before_awakening[-6] if len(readings_before_awakening) >= 6 else readings_before_awakening[0]
            after_reading = readings_before_awakening[-1]
            correlation_params = generate_correlation_parameters(before_reading, after_reading)
            ai_insight = generate_ai_insight(correlation_params, baby_data["first_name"])
        else:
            correlation_params = {}
            ai_insight = f"{baby_data['first_name']} woke up naturally."
        
        last_reading = readings_before_awakening[-1] if readings_before_awakening else None
        
        awakening_event = {
            "sleep_started_at": session_start.isoformat(),
            "awakened_at": awake_time.isoformat(),
            "sleep_duration_minutes": round(sleep_duration, 1),
            "ai_insight": ai_insight,
            "last_sensor_readings": {
                "temp_celcius": last_reading["temp_celcius"] if last_reading else None,
                "humidity": last_reading["humidity"] if last_reading else None,
                "noise_decibel": last_reading["noise_decibel"] if last_reading else None,
                "heart_rate": last_reading["heart_rate"] if last_reading else None,
            } if last_reading else None,
            "correlation_params": correlation_params,
        }
        awakening_events.append(awakening_event)
        
        # Add awakening alert
        alerts.append({
            "type": "awakening",
            "title": f"{baby_data['first_name']} Woke Up",
            "message": f"{baby_data['first_name']} woke up after {format_duration(sleep_duration)} of sleep.",
            "severity": "info",
            "metadata": {
                "sleep_duration_minutes": sleep_duration,
                "sleep_started_at": session_start.isoformat(),
            },
            "created_at": awake_time,
        })
        
        # Start new session (baby goes back to sleep after short wake period)
        session_start = awake_time + timedelta(minutes=random.randint(5, 20))
        current_time = session_start
        readings_before_awakening = []
    
    # Generate nap data
    for nap_start_time, nap_end_time in schedule["naps"]:
        # Random variation in nap times
        start_variation = random.randint(-15, 15)
        end_variation = random.randint(-15, 15)
        
        nap_start = datetime.combine(day, datetime.min.time().replace(
            hour=nap_start_time[0], minute=nap_start_time[1]
        )) + timedelta(minutes=start_variation)
        
        nap_end = datetime.combine(day, datetime.min.time().replace(
            hour=nap_end_time[0], minute=nap_end_time[1]
        )) + timedelta(minutes=end_variation)
        
        # Skip some naps randomly (babies don't always nap on schedule)
        if random.random() < 0.15:
            continue
        
        # Generate sensor readings during nap
        current_time = nap_start
        readings_before_awakening = []
        
        while current_time < nap_end:
            reading = generate_sensor_reading(
                base_temp, base_humidity, base_noise, hr_range
            )
            reading["datetime"] = current_time
            reading["sleep_quality_score"] = generate_sleep_quality_score(
                reading["temp_celcius"],
                reading["humidity"],
                reading["noise_decibel"],
            )
            sensor_readings.append(reading)
            readings_before_awakening.append(reading)
            current_time += timedelta(minutes=SENSOR_INTERVAL_MINUTES)
        
        # Record nap awakening
        nap_duration = (nap_end - nap_start).total_seconds() / 60
        last_reading = readings_before_awakening[-1] if readings_before_awakening else None
        
        if len(readings_before_awakening) >= 2:
            before_reading = readings_before_awakening[0]
            after_reading = readings_before_awakening[-1]
            correlation_params = generate_correlation_parameters(before_reading, after_reading)
        else:
            correlation_params = {}
        
        awakening_event = {
            "sleep_started_at": nap_start.isoformat(),
            "awakened_at": nap_end.isoformat(),
            "sleep_duration_minutes": round(nap_duration, 1),
            "ai_insight": f"{baby_data['first_name']} completed a nap. Sleep quality was good.",
            "last_sensor_readings": {
                "temp_celcius": last_reading["temp_celcius"] if last_reading else None,
                "humidity": last_reading["humidity"] if last_reading else None,
                "noise_decibel": last_reading["noise_decibel"] if last_reading else None,
                "heart_rate": last_reading["heart_rate"] if last_reading else None,
            } if last_reading else None,
            "correlation_params": correlation_params,
        }
        awakening_events.append(awakening_event)
    
    return sensor_readings, awakening_events, alerts


async def seed_sleep_realtime_data(
    session,
    baby_ids: List[int],
    user_ids: List[int],
):
    """Generate 90 days of sleep data for all babies."""
    print(f"Seeding {DAYS_OF_DATA} days of sleep data...")
    
    all_sensor_data = {baby_id: [] for baby_id in baby_ids}
    all_awakenings = {baby_id: [] for baby_id in baby_ids}
    all_alerts = {baby_id: [] for baby_id in baby_ids}
    
    for i, baby_id in enumerate(baby_ids):
        baby_data = BABIES_DATA[i]
        user_id = user_ids[i]
        
        print(f"\n  Generating data for {baby_data['first_name']}...")
        
        for day_offset in range(DAYS_OF_DATA):
            day = date.today() - timedelta(days=day_offset)
            
            sensor_readings, awakenings, alerts = await seed_sleep_data_for_day(
                session, baby_id, baby_data, day, user_id
            )
            
            all_sensor_data[baby_id].extend(sensor_readings)
            all_awakenings[baby_id].extend(awakenings)
            all_alerts[baby_id].extend(alerts)
            
            if day_offset % 30 == 0:
                print(f"    - Processed {day_offset + 1}/{DAYS_OF_DATA} days")
        
        # Insert sensor data in batches for better performance
        sensor_data = all_sensor_data[baby_id]
        print(f"    - Inserting {len(sensor_data)} sensor readings in batches of {BATCH_SIZE}...")
        for batch_start in range(0, len(sensor_data), BATCH_SIZE):
            batch = sensor_data[batch_start:batch_start + BATCH_SIZE]
            if batch:
                # Build batch insert values
                values_list = []
                params = {"baby_id": baby_id}
                for idx, reading in enumerate(batch):
                    values_list.append(f"(:baby_id, :dt{idx}, :hum{idx}, :temp{idx}, :noise{idx}, :hr{idx}, :sq{idx})")
                    params[f"dt{idx}"] = reading["datetime"]
                    params[f"hum{idx}"] = reading["humidity"]
                    params[f"temp{idx}"] = reading["temp_celcius"]
                    params[f"noise{idx}"] = reading["noise_decibel"]
                    params[f"hr{idx}"] = reading["heart_rate"]
                    params[f"sq{idx}"] = reading["sleep_quality_score"]
                
                values_sql = ", ".join(values_list)
                await session.execute(
                    text(f'''
                        INSERT INTO "Nappi"."sleep_realtime_data"
                        (baby_id, datetime, humidity, temp_celcius, noise_decibel, heart_rate, sleep_quality_score)
                        VALUES {values_sql}
                    '''),
                    params
                )
            if batch_start % 2000 == 0 and batch_start > 0:
                print(f"      - Inserted {batch_start}/{len(sensor_data)} readings...")
                await session.commit()
        
        # Insert awakening events
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
            
            # Insert correlation if we have parameters
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
        
        # Insert alerts in batches (limit to avoid too many)
        alerts_to_insert = all_alerts[baby_id][:100]  # Cap at 100 alerts per baby
        print(f"    - Inserting {len(alerts_to_insert)} alerts...")
        for batch_start in range(0, len(alerts_to_insert), 50):
            batch = alerts_to_insert[batch_start:batch_start + 50]
            if batch:
                values_list = []
                params = {"baby_id": baby_id, "user_id": user_id}
                for idx, alert in enumerate(batch):
                    values_list.append(f"(:baby_id, :user_id, :type{idx}, :title{idx}, :msg{idx}, :sev{idx}, CAST(:meta{idx} AS jsonb), :read{idx}, :cat{idx})")
                    params[f"type{idx}"] = alert["type"]
                    params[f"title{idx}"] = alert["title"]
                    params[f"msg{idx}"] = alert["message"]
                    params[f"sev{idx}"] = alert["severity"]
                    params[f"meta{idx}"] = json.dumps(alert.get("metadata", {}))
                    params[f"read{idx}"] = random.random() < 0.7
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
    
    return all_sensor_data, all_awakenings


async def seed_daily_summaries(
    session,
    baby_ids: List[int],
    all_sensor_data: Dict[int, List[Dict]],
    all_awakenings: Dict[int, List[Dict]],
):
    """Compute and insert daily summaries for each baby."""
    print("\nSeeding daily summaries...")
    
    for i, baby_id in enumerate(baby_ids):
        baby_data = BABIES_DATA[i]
        sensor_data = all_sensor_data[baby_id]
        awakenings = all_awakenings[baby_id]
        
        # Group data by date
        data_by_date: Dict[date, List[Dict]] = {}
        for reading in sensor_data:
            reading_date = reading["datetime"].date()
            if reading_date not in data_by_date:
                data_by_date[reading_date] = []
            data_by_date[reading_date].append(reading)
        
        # Group awakenings by date
        awakenings_by_date: Dict[date, List[Dict]] = {}
        for event in awakenings:
            awakened_at = datetime.fromisoformat(event["awakened_at"])
            event_date = awakened_at.date()
            if event_date not in awakenings_by_date:
                awakenings_by_date[event_date] = []
            awakenings_by_date[event_date].append(event)
        
        summaries_created = 0
        for summary_date, readings in data_by_date.items():
            if not readings:
                continue
            
            # Calculate averages
            avg_temp = sum(r["temp_celcius"] for r in readings) / len(readings)
            avg_humidity = sum(r["humidity"] for r in readings) / len(readings)
            avg_noise = sum(r["noise_decibel"] for r in readings) / len(readings)
            
            # Count awakenings by time period
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
            
            # Detect anomalies
            anomalies = {}
            if avg_temp > 23:
                anomalies["high_temperature"] = {"avg": round(avg_temp, 1), "threshold": 23}
            if avg_temp < 19:
                anomalies["low_temperature"] = {"avg": round(avg_temp, 1), "threshold": 19}
            if avg_humidity > 60:
                anomalies["high_humidity"] = {"avg": round(avg_humidity, 1), "threshold": 60}
            if avg_humidity < 40:
                anomalies["low_humidity"] = {"avg": round(avg_humidity, 1), "threshold": 40}
            
            await session.execute(
                text('''
                    INSERT INTO "Nappi"."daily_summary"
                    (baby_id, summary_date, avg_temp, avg_humidity, avg_noise,
                     morning_awakes_sum, noon_awakes_sum, night_awakes_sum, anomalies)
                    VALUES (:baby_id, :summary_date, :avg_temp, :avg_humidity, :avg_noise,
                            :morning_awakes_sum, :noon_awakes_sum, :night_awakes_sum,
                            CAST(:anomalies AS jsonb))
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
                    "anomalies": json.dumps(anomalies) if anomalies else None,
                }
            )
            summaries_created += 1
        
        print(f"  - Created {summaries_created} daily summaries for {baby_data['first_name']}")
    
    await session.commit()


async def seed_optimal_stats(
    session,
    baby_ids: List[int],
    all_sensor_data: Dict[int, List[Dict]],
):
    """Compute and insert optimal stats for each baby."""
    print("\nSeeding optimal stats...")
    
    for i, baby_id in enumerate(baby_ids):
        baby_data = BABIES_DATA[i]
        sensor_data = all_sensor_data[baby_id]
        hr_range = HEART_RATE_RANGES[baby_data["age_category"]]
        
        if not sensor_data:
            continue
        
        # Find readings with high sleep quality scores
        high_quality_readings = [r for r in sensor_data if r.get("sleep_quality_score", 0) >= 80]
        
        if high_quality_readings:
            optimal_temp = sum(r["temp_celcius"] for r in high_quality_readings) / len(high_quality_readings)
            optimal_humidity = sum(r["humidity"] for r in high_quality_readings) / len(high_quality_readings)
            optimal_noise = sum(r["noise_decibel"] for r in high_quality_readings) / len(high_quality_readings)
            optimal_hr = sum(r["heart_rate"] for r in high_quality_readings) / len(high_quality_readings)
        else:
            # Fallback to ideal values
            optimal_temp = TEMP_OPTIMAL
            optimal_humidity = HUMIDITY_OPTIMAL
            optimal_noise = NOISE_OPTIMAL
            optimal_hr = sum(hr_range) / 2
        
        await session.execute(
            text('''
                INSERT INTO "Nappi"."optimal_stats"
                (baby_id, temperature, humidity, noise, heart_rate)
                VALUES (:baby_id, :temperature, :humidity, :noise, :heart_rate)
            '''),
            {
                "baby_id": baby_id,
                "temperature": round(optimal_temp, 1),
                "humidity": round(optimal_humidity, 1),
                "noise": round(optimal_noise, 1),
                "heart_rate": round(optimal_hr, 0),
            }
        )
        
        print(f"  - Created optimal stats for {baby_data['first_name']}: "
              f"temp={round(optimal_temp, 1)}°C, humidity={round(optimal_humidity, 1)}%, "
              f"noise={round(optimal_noise, 1)}dB")
    
    await session.commit()


async def print_validation_summary(session):
    """Print summary of seeded data for validation."""
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
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
    
    print("\n" + "-" * 60)
    print("Demo Login Credentials:")
    print("-" * 60)
    print("  Username: demo@nappi.app")
    print("  Password: demo123")
    print("=" * 60)


# =============================================================================
# Main Entry Point
# =============================================================================

async def seed_database():
    """Main function to seed the database with demo data."""
    print("\n" + "=" * 60)
    print("NAPPI DEMO DATA SEEDER")
    print("=" * 60)
    print(f"WARNING: This will DELETE all existing data!")
    print(f"Generating {DAYS_OF_DATA} days of data for {len(BABIES_DATA)} babies...")
    print("=" * 60 + "\n")
    
    # Set random seed for reproducibility
    set_seed(SEED)
    
    # Connect to database
    db = get_database()
    await db.connect(settings.DATABASE_URL)
    
    try:
        async with db.session() as session:
            # 1. Truncate all tables
            await truncate_tables(session)
            
            # 2. Seed babies
            baby_ids = await seed_babies(session)
            
            # 3. Seed users linked to babies
            user_ids = await seed_users(session, baby_ids)
            
            # 4. Seed baby notes
            await seed_baby_notes(session, baby_ids)
            
            # 5. Seed sleep data (sensor readings, awakenings, correlations, alerts)
            all_sensor_data, all_awakenings = await seed_sleep_realtime_data(
                session, baby_ids, user_ids
            )
            
            # 6. Seed daily summaries
            await seed_daily_summaries(
                session, baby_ids, all_sensor_data, all_awakenings
            )
            
            # 7. Seed optimal stats
            await seed_optimal_stats(session, baby_ids, all_sensor_data)
            
            # 8. Print validation summary
            await print_validation_summary(session)
        
        print("\nSeeding completed successfully!")
        
    except Exception as e:
        print(f"\nError during seeding: {e}")
        raise
    finally:
        await db.disconnect()


def main():
    """Entry point for running as a module."""
    asyncio.run(seed_database())


if __name__ == "__main__":
    main()
