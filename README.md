# Nappi Baby Monitor API

Backend API for baby sleep and room monitoring system. This FastAPI application tracks sleep patterns, monitors room conditions (temperature, humidity, noise), provides AI-powered insights via Google Gemini, and delivers real-time alerts through SSE and Web Push.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Smart Features](#smart-features)
- [Statistics Page Guide](#statistics-page-guide)
- [Database Tables](#database-tables)
- [Scheduled Jobs](#scheduled-jobs)
- [Sleep Blocks](#sleep-blocks)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Sleep Guidelines Sources](#sleep-guidelines-sources)

---

## Project Overview

**Nappi** is a baby monitoring system that:
- Tracks sleep patterns and quality
- Monitors room environment (temperature, humidity, noise - 3 sensors only)
- Collects data from IoT sensors (M5 devices) every 5 seconds during sleep
- Analyzes awakening correlations with AI-powered insights (Google Gemini)
- Learns optimal sleep conditions for each baby via weighted averages
- Predicts next sleep windows using age-based wake window guidelines
- Delivers real-time alerts via SSE (Server-Sent Events) and optional Web Push
- Provides an AI chat with full baby context (sleep history, patterns, room conditions)
- Groups raw awakening events into consolidated sleep blocks for accurate session counts

---

## Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) - async Python web framework
- **Database**: PostgreSQL (Neon serverless) with [SQLAlchemy 2.0](https://www.sqlalchemy.org/) async - raw SQL via `text()`, no ORM
- **Background Jobs**: [APScheduler](https://apscheduler.readthedocs.io/) (AsyncIOScheduler)
- **HTTP Client**: [aiohttp](https://docs.aiohttp.org/) - sensor API polling
- **Data Validation**: [Pydantic](https://docs.pydantic.dev/) v2
- **AI**: [Google Gemini](https://ai.google.dev/) (`gemini-2.5-flash`) - chat, insights, trends. Sync SDK, run in executor.
- **Real-time**: SSE via `asyncio.Queue` per user connection
- **Push Notifications**: [pywebpush](https://github.com/web-push-libs/pywebpush) with VAPID

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                       # FastAPI app, CORS, lifespan (startup/shutdown)
│   │
│   ├── api/                          # API Layer (8 routers)
│   │   ├── endpoints.py              # Dashboard: /sleep/latest, /room/current
│   │   ├── sensor_events.py          # Sensor events: sleep-start/end, intervention, cooldown
│   │   ├── stats.py                  # Statistics: sensors, patterns, daily-sleep, trends, schedule, AI summary
│   │   ├── alerts.py                 # Alerts: SSE stream, history, read/delete, push subscribe
│   │   ├── chat.py                   # AI chat: POST /chat
│   │   ├── babies.py                 # Baby notes CRUD
│   │   ├── auth.py                   # Auth: signup, signin, register-baby, change-password
│   │   └── models.py                 # Pydantic request/response models
│   │
│   ├── core/                         # Core Infrastructure
│   │   ├── database.py               # DatabaseManager singleton (async SQLAlchemy)
│   │   ├── settings.py               # Configuration from env vars
│   │   └── utils.py                  # Sensor endpoint/column mappings (3 sensors)
│   │
│   ├── services/                     # Business Logic
│   │   ├── scheduler.py              # APScheduler: 3 jobs (sensors, daily summary, optimal stats)
│   │   ├── tasks.py                  # Sensor collection task (every 5s, sleeping babies only)
│   │   ├── data_miner.py             # HTTP client for sensor APIs (aiohttp, 5s timeout)
│   │   ├── babies_data.py            # All DB operations (queries, inserts, upserts)
│   │   ├── sleep_state.py            # In-memory sleep state + intervention cooldowns
│   │   ├── alert_service.py          # Alert creation + SSEManager + threshold checks
│   │   ├── push_service.py           # Web Push subscriptions + VAPID delivery
│   │   ├── correlation_analyzer.py   # Sensor change analysis + Gemini insights
│   │   ├── chat_service.py           # Full baby context builder + Gemini chat
│   │   ├── trend_analyzer.py         # 7/30-day trends + consistency scores + AI summary
│   │   ├── schedule_predictor.py     # Next sleep prediction + age-based wake windows
│   │   ├── sleep_patterns.py         # Gap-based sleep pattern clustering (2h threshold)
│   │   ├── daily_summary.py          # Daily aggregation job (10:00 AM Israel)
│   │   ├── optimal_stats.py          # Weighted avg of best conditions (10:05 AM Israel)
│   │   └── auth_manager.py           # User/baby signup, signin, password change
│   │
│   ├── utils/
│   │   └── sleep_blocks.py           # Groups awakening events into consolidated sleep blocks
│   │
│   └── db/
│       ├── models.py                 # Pydantic models matching DB schema
│       ├── generate_models.py        # Auto-generate models from DB
│       └── seed_demo_data.py         # Demo data seeder (3 babies, 90 days)
│
├── migrations/
│   ├── 001_create_alerts_table.sql   # Creates alerts + push_subscriptions tables
│   └── 002_add_baby_notes.sql        # Adds notes column to babies table
│
├── requirements.txt
└── .env                              # Environment variables (not tracked)
```

---

## Getting Started

### Prerequisites

- **Python**: 3.10+
- **PostgreSQL**: 13+ (or Neon serverless)
- **pip**: Latest version

### 1. Clone and Setup

```bash
git clone <repository-url>
cd nappi-project/backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the `backend/` directory:

```bash
# Database (required)
DB_CONNECTION_STRING=postgresql+asyncpg://user:password@host:5432/dbname

# AI Insights (required for chat/insights)
GEMINI_API_KEY=your_gemini_api_key

# Sensors
SENSOR_API_BASE_URL=http://your-sensor-device:8080
SENSOR_POLL_INTERVAL_SECONDS=5

# Daily Jobs
DAILY_SUMMARY_HOUR=10
DAILY_SUMMARY_TIMEZONE=Asia/Jerusalem

# Web Push (optional)
VAPID_PUBLIC_KEY=your_vapid_public_key
VAPID_PRIVATE_KEY=your_vapid_private_key
VAPID_EMAIL=admin@nappi.app

# Logging
LOG_LEVEL=INFO
```

### 3. Seed Demo Data (Optional)

```bash
python -m app.db.seed_demo_data
```

**WARNING**: This will DELETE all existing data.

After seeding, log in with:
- `demo@nappi.app` / `demo123` (baby: Emma Cohen, 3mo)
- `david@nappi.app` / `david123` (baby: Noah Levy, 7mo)
- `maya@nappi.app` / `maya123` (baby: Mia Ben-David, 14mo)

---

## Configuration

Configuration lives in `app/core/settings.py`, loaded from environment variables.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_CONNECTION_STRING` | - | PostgreSQL connection string (asyncpg) |
| `GEMINI_API_KEY` | - | Google Gemini API key |
| `GEMINI_MODEL_CHAT` | `models/gemini-2.5-flash` | Model for chat |
| `GEMINI_MODEL_INSIGHTS` | `models/gemini-2.5-flash` | Model for insights |
| `SENSOR_API_BASE_URL` | `http://localhost:8001` | Sensor hub URL |
| `SENSOR_POLL_INTERVAL_SECONDS` | `5` | Sensor polling interval |
| `CORRELATION_TIME_WINDOW_MINUTES` | `60` | Time window to analyze before awakening |
| `DAILY_SUMMARY_HOUR` | `10` | Hour to run daily jobs (24h) |
| `DAILY_SUMMARY_TIMEZONE` | `Asia/Jerusalem` | Timezone for daily jobs |
| `VAPID_PUBLIC_KEY` | - | Web Push public key |
| `VAPID_PRIVATE_KEY` | - | Web Push private key |
| `VAPID_EMAIL` | `admin@nappi.app` | VAPID contact email |
| `LOG_LEVEL` | `INFO` | Logging level |

### Per-Sensor Correlation Thresholds

Configured as a dict in `settings.py` (not env var):

```python
CORRELATION_CHANGE_THRESHOLDS: dict = {
    "temp_celcius": 5.0,     # 5% change triggers correlation
    "humidity": 5.0,         # 5% change
    "noise_decibel": 100.0,  # effectively disabled
}
```

### Sensor Mapping (`app/core/utils.py`)

3 sensors only:

```python
SENSOR_TO_ENDPOINT_MAP = {
    "temperature": "/temperature/{baby_id}",
    "humidity": "/humidity/{baby_id}",
    "noise_decibel": "/noise_decibel/{baby_id}",
}
```

---

## Running the Application

```bash
# Development (with auto-reload)
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## API Endpoints

### Auth (`/auth`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/signup` | Create user, search for existing baby by name+birthdate |
| `POST` | `/auth/signin` | Login, return user + baby |
| `POST` | `/auth/register-baby` | Create baby + link to user |
| `POST` | `/auth/change-password` | Update password |

### Dashboard (`/sleep`, `/room`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/sleep/latest?baby_id=X` | Last sleep summary (duration, quality, avg temp/humidity, max noise) |
| `GET` | `/room/current?baby_id=X` | Current room sensor readings (all Optional, no fake defaults) |

**`/sleep/latest` response:**
```json
{
  "baby_name": "Emma",
  "started_at": "2026-02-19T22:00:00",
  "ended_at": "2026-02-20T06:30:00",
  "total_sleep_minutes": 510,
  "awakenings_count": 2,
  "avg_temperature": 21.5,
  "avg_humidity": 48.0,
  "max_noise": 42.0
}
```

**`/room/current` response:**
```json
{
  "temperature_c": 22.1,
  "humidity_percent": 47.0,
  "noise_db": 32.5,
  "measured_at": "2026-02-20T12:00:00Z"
}
```

### Sensor Events (`/sensor`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sensor/sleep-start` | Baby fell asleep - start sensor collection |
| `POST` | `/sensor/sleep-end` | Baby woke up - record event, trigger AI insight + alert |
| `POST` | `/sensor/baby-away` | Baby left sensor area - stop collection, no event |
| `GET` | `/sensor/sleep-status/{baby_id}` | Is baby sleeping? |
| `GET` | `/sensor/sleeping-babies` | All currently sleeping babies |
| `POST` | `/sensor/intervention` | Parent override (mark_asleep/mark_awake) - 20min cooldown |
| `GET` | `/sensor/cooldown-status/{baby_id}` | Check intervention cooldown |

### Statistics (`/stats`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/stats/sensors` | Sensor averages over time (7-90 day range) |
| `GET` | `/stats/sleep-patterns` | Sleep time patterns with clustering |
| `GET` | `/stats/daily-sleep` | Daily sleep totals (session counts use sleep blocks) |
| `GET` | `/stats/insights` | AI-powered awakening analysis |
| `GET` | `/stats/insights-enhanced` | Structured AI analysis (5 sections) |
| `GET` | `/stats/optimal` | Learned optimal conditions (3 sensors) |
| `GET` | `/stats/trends` | 7/30-day trends + AI summary |
| `GET` | `/stats/schedule-prediction` | Next sleep prediction + wake windows |
| `GET` | `/stats/ai-summary` | Home dashboard AI summary |

### Alerts & Push (`/alerts`, `/push`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/alerts/stream?user_id=X` | SSE stream for real-time alerts |
| `GET` | `/alerts/history` | Alert history (paginated, filterable) |
| `GET` | `/alerts/unread-count` | Count of unread alerts |
| `POST` | `/alerts/{id}/read` | Mark single alert as read |
| `POST` | `/alerts/read-all` | Mark all alerts as read |
| `DELETE` | `/alerts` | Bulk delete alerts by IDs (max 100) |
| `GET` | `/push/vapid-key` | Public VAPID key for client subscription |
| `GET` | `/push/status` | Is user subscribed to push? |
| `POST` | `/push/subscribe` | Save push subscription |
| `POST` | `/push/unsubscribe` | Remove push subscription |

### Baby Notes (`/babies`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/babies/{baby_id}/notes` | List all notes |
| `POST` | `/babies/{baby_id}/notes` | Create note |
| `PUT` | `/babies/{baby_id}/notes/{note_id}` | Update note |
| `DELETE` | `/babies/{baby_id}/notes/{note_id}` | Delete note |

### Chat (`/chat`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat` | AI chat with full baby context (60s timeout) |

**Request body:**
```json
{
  "baby_id": 10,
  "user_id": 13,
  "message": "Why is Emma waking up so much?",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
}
```

---

## Smart Features

### 1. Correlation Analysis

**When**: Triggered every time a baby wakes up (`/sensor/sleep-end`)

- Looks at the last 60 minutes of sensor data before awakening
- Compares first 25% of readings vs last 25% of readings
- Calculates percentage change for each sensor (temp, humidity, noise)
- Uses **per-parameter thresholds** (configured in `settings.py`)
- Stored in: `correlations.parameters`

### 2. Gemini AI Insights (Three Types)

#### A) Quick Insights (Automatic)
- Triggered automatically on every `/sensor/sleep-end` event
- 1-2 sentence explanation with one gentle suggestion
- Stored in: `awakening_events.event_metadata.ai_insight`

#### B) Standard Insights (On-Demand)
- `GET /stats/insights?baby_id=X&event_id=Y`
- Full analysis with environmental changes and baby context
- 3-4 sentence analysis with actionable advice

#### C) Enhanced Insights (Structured)
- `GET /stats/insights-enhanced?baby_id=X&event_id=Y`
- Returns structured sections: `likely_cause`, `actionable_tips`, `environment_assessment`, `age_context`, `sleep_quality_note`

### 3. AI Chat

- Builds full baby context: profile, notes, optimal stats, last 5 awakenings (as sleep blocks), correlations, 7-day summaries, sleep patterns, current room
- Source-cited age-specific guidelines (Cleveland Clinic, AAP, Sleep Foundation)
- Gentle, supportive tone - never alarming

### 4. Optimal Conditions Calculator

**When**: Daily at 10:05 AM Israel time

```
weight = 1 / (1 + total_awakenings)
optimal_value = SUM(value * weight) / SUM(weight)
```

Days with fewer awakenings get higher weight - result represents conditions that historically worked best.

### 5. Schedule Prediction

- Predicts next sleep time based on age-specific wake windows (Cleveland Clinic)
- Source-cited bedtimes (Sleep Foundation)
- Returns: predicted time, confidence level, wake window status, suggestions

### 6. Real-time Alerts

- SSE streaming via `asyncio.Queue` per user (supports multiple tabs)
- Alert thresholds: temp < 18°C or > 26°C, humidity < 30% or > 60%, noise > 50dB
- All alert messages use gentle tone ("We noticed...", "you might want to...")
- Optional Web Push notifications via VAPID

### 7. Sleep Block Grouping

Groups raw awakening events into consolidated sleep blocks (30min gap threshold). A night sleep with 2 brief wake-ups = 1 sleep block, not 3 separate sessions. Used across: daily-sleep counts, chat context, correlation counts, trend analysis.

---

## Statistics Page Guide

### 1. Sensor Data Over Time (`/stats/sensors`)

```
GET /stats/sensors?baby_id=1&sensor=temperature&start_date=2026-01-01&end_date=2026-01-14
```

Returns daily averages from `daily_summary` table. Supports: `temperature`, `humidity`, `noise`. These are averages during sleep only.

### 2. Sleep Patterns (`/stats/sleep-patterns`)

```
GET /stats/sleep-patterns?baby_id=1&month=2&year=2026
```

Clusters sleep sessions by time of day using a **gap-based algorithm** (2-hour threshold). This is the data shown in the **Sleep Patterns** chart on the Statistics page.

### 3. Sleep Pattern Clustering Algorithm

Implemented in `app/services/sleep_patterns.py`.

**How it works:**

1. Convert each session's start time to decimal hours (e.g., 8:30 → 8.5)
2. Sort all sessions by start hour (time of day, ignoring date)
3. Walk through sorted sessions - if the gap between consecutive start times > 2h, start a new cluster
4. Label each cluster by its average start hour:
   - `5:00–11:00` → "Morning nap"
   - `11:00–17:00` → "Afternoon nap"
   - Otherwise → "Night sleep"
5. Compute per-cluster stats: avg start/end, avg duration, session count, earliest/latest range

**Walkthrough example:**

Given 8 sleep sessions recorded over a month:

| Session | Start | End   |
|---------|-------|-------|
| A       | 09:00 | 10:15 |
| B       | 09:30 | 10:45 |
| C       | 08:45 | 10:00 |
| D       | 13:00 | 14:30 |
| E       | 13:15 | 14:00 |
| F       | 20:30 | 06:15 |
| G       | 20:00 | 05:45 |
| H       | 21:00 | 06:30 |

**Step 1 - Sort by start hour (decimal):**

```
C(8.75) → A(9.0) → B(9.5) → D(13.0) → E(13.25) → G(20.0) → F(20.5) → H(21.0)
```

**Step 2 - Cluster using 2h gap threshold:**

```
C ─0.25h─ A ─0.5h─ B ──3.5h──> D ─0.25h─ E ──6.75h──> G ─0.5h─ F ─0.5h─ H
|____Cluster 1____|   (gap!)   |_Cluster 2_|   (gap!)   |____Cluster 3____|
```

- **Cluster 1**: C, A, B - gaps of 0.25h and 0.5h (both < 2h)
- **Cluster 2**: D, E - gap of 0.25h (< 2h)
- **Cluster 3**: G, F, H - gaps of 0.5h and 0.5h (both < 2h)

**Step 3 - Label & compute averages:**

| Cluster | Label          | Avg Start | Avg End | Avg Duration | Sessions | Range        |
|---------|----------------|-----------|---------|--------------|----------|--------------|
| 1       | Morning nap    | 09:05     | 10:20   | 1.25h        | 3        | 08:45–10:45  |
| 2       | Afternoon nap  | 13:07     | 14:15   | 1.12h        | 2        | 13:00–14:30  |
| 3       | Night sleep    | 20:30     | 06:10   | 9.67h        | 3        | 20:00–06:30  |

> **Note:** Overnight sessions (e.g., 20:30→06:15) use adjusted end hours internally (06:15 → 30.25) to compute correct averages, then convert back to 24h format via `% 24`.

### 4. Daily Sleep Totals (`/stats/daily-sleep`)

```
GET /stats/daily-sleep?baby_id=1&start_date=2026-02-01&end_date=2026-02-14
```

Returns total sleep hours + session count per day. Session counts use sleep blocks (not raw events).

### 5. Awakenings per Session (Statistics Page Chart)

The **Awakenings per Session** chart on the Statistics page shows how sleep quality is trending over time. It plots a single metric per day: the average number of times the baby woke up within each sleep session.

**Calculation:**

1. Fetch all awakening events for the selected date range via `GET /stats/daily-sleep`
2. Group raw events into **sleep blocks** using `group_into_sleep_blocks()` (30-minute gap threshold)
3. For each sleep block, `interruption_count = number of events in block - 1` (e.g., a block with 3 events had 2 awakenings)
4. Per day: sum all `interruption_count` values across blocks, divide by the number of blocks (sessions)

```
awakenings_per_session = total_awakenings_that_day / total_sessions_that_day
```

**Example:**

| Day | Sessions (blocks) | Awakenings (interruptions) | Ratio |
|-----|-------------------|---------------------------|-------|
| Feb 18 | 3 (morning nap, afternoon nap, night sleep) | 4 (0 + 1 + 3) | 1.3 |
| Feb 19 | 2 (afternoon nap, night sleep) | 1 (0 + 1) | 0.5 |
| Feb 20 | 3 | 2 | 0.7 |

**How to read it:**

- **Line going down** = improvement - baby is sleeping more continuously with fewer interruptions
- **Line going up** = more fragmented sleep - baby is waking more often within sessions
- **Value of 0** = no awakenings at all - every session was uninterrupted
- **Value of 1** = on average, baby woke once per session

This metric is more useful than raw awakening counts because it normalizes against the number of sessions. A day with 4 awakenings across 4 naps (ratio 1.0) is very different from 4 awakenings in a single night sleep (ratio 4.0).

### 6. Trends (`/stats/trends`)

```
GET /stats/trends?baby_id=1
```

Returns 7-day and 30-day trends:
- `trend`: "improving" / "stable" / "declining" (compares first half vs second half)
- `consistency_score`: 1 - (std_dev / mean), range 0-1
- `ai_insights`: Gemini-generated summary, highlights, things to watch, suggestions

### 7. Date Range Validation

| Rule | Value |
|------|-------|
| Minimum range | 7 days |
| Maximum range | 90 days |

---

## Database Tables

All tables under schema `"Nappi"` (double-quoted, case-sensitive in all queries).

| Table | Purpose |
|-------|---------|
| `users` | User accounts (username, password, baby_id FK) |
| `babies` | Baby profiles (name, birthdate, gender, notes) |
| `sleep_realtime_data` | Raw sensor readings every 5s during sleep (deleted daily after summary) |
| `awakening_events` | Sleep end events + JSONB metadata (timestamps, sensors, AI insight) |
| `correlations` | Sensor changes before awakening + AI insights |
| `daily_summary` | Daily averages + morning/noon/night awakening counts |
| `optimal_stats` | Learned best conditions per baby (3 sensors, updated daily) |
| `alerts` | Alert history (type, severity, message, read status) |
| `push_subscriptions` | Web Push subscription data per user |
| `baby_notes` | Multi-entry notes with title/content per baby |

### Awakening Events Metadata Structure

```json
{
  "sleep_started_at": "2026-02-19T22:00:00",
  "awakened_at": "2026-02-20T06:30:00",
  "sleep_duration_minutes": 510.0,
  "last_sensor_readings": {
    "temp_celcius": 21.5,
    "humidity": 48.0,
    "noise_decibel": 35.0
  },
  "ai_insight": "The room stayed comfortable through the night. This looks like a natural waking for Emma's age."
}
```

### Notes

- Two separate notes systems: `babies.notes` (single text column for health info) and `baby_notes` table (multi-entry CRUD)
- All queries must use `"Nappi"."table_name"` schema prefix

---

## Scheduled Jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| **Sensor Collection** | Every 5 seconds | Polls 3 sensors for sleeping babies only (parallel per baby + sensor) |
| **Daily Summary** | 10:00 AM Israel | Aggregates sensor data, counts awakenings by time period, deletes raw data |
| **Optimal Stats** | 10:05 AM Israel | Calculates weighted avg of best conditions per baby |

---

## Sleep Blocks

`app/utils/sleep_blocks.py` groups consecutive awakening events into logical sleep blocks.

**Example**: Night sleep 9 PM to 6 AM with 2 brief wake-ups = 1 sleep block with 2 interruptions (not 3 separate sessions).

- Gap threshold: 30 minutes
- Returns per block: `block_start`, `block_end`, `total_sleep_minutes`, `interruption_count`, `events[]`
- Used in: `stats.py` (daily-sleep), `chat_service.py`, `correlation_analyzer.py`, `trend_analyzer.py`

---

## Development

### Database Pattern

```python
from app.core.database import get_database
from sqlalchemy import text

db = get_database()

async with db.session() as session:
    result = await session.execute(
        text('SELECT * FROM "Nappi"."babies" WHERE id = :id'),
        {"id": baby_id}
    )
    row = result.mappings().first()  # dict or None
    # For writes: await session.commit()
```

### Gemini Pattern

```python
# Gemini SDK is synchronous - MUST run in executor
loop = asyncio.get_event_loop()
response = await loop.run_in_executor(
    None,
    lambda: client.models.generate_content(model=..., contents=..., config=...)
)
```

### AI Tone Guidelines

All Gemini prompts enforce:
- Soft language: "we noticed", "you might want to", "it could help"
- No dramatic words: "significant", "critical", "alarming", "drastic"
- Frame suggestions as options, not commands
- Alert messages also use gentle tone

### Key Dependencies

```
fastapi, uvicorn[standard], pydantic>=2.0, aiohttp, apscheduler,
python-dotenv, sqlalchemy[asyncio], asyncpg, google-genai>=1.0,
pytz, pywebpush, certifi
```

---

## Troubleshooting

### Cannot connect to database

```bash
# Check connection string in .env (must use asyncpg driver)
DB_CONNECTION_STRING=postgresql+asyncpg://user:pass@host:5432/dbname
```

### Gemini API errors

- **429 Rate Limit**: System falls back gracefully - correlation saved without AI insights
- **SSL errors on macOS**: `pip install certifi`

### Scheduler not running

1. Check logs for scheduler initialization on startup
2. Verify `SENSOR_API_BASE_URL` points to the sensor device
3. Baby must be marked sleeping via `/sensor/sleep-start` for data collection

### CORS errors

Add your frontend URL to `CORS_ORIGINS` in `app/core/settings.py`:

```python
CORS_ORIGINS: list = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://your-frontend-url",
]
```

---

## Sleep Guidelines Sources

The AI chat (`chat_service.py`) and schedule predictor (`schedule_predictor.py`) use age-specific sleep guidelines verified against authoritative medical sources.

### Sources Used

| Source | What We Use It For |
|--------|-------------------|
| **AAP/AASM** - [AAP endorses AASM consensus](https://publications.aap.org/aapnews/news/6630/AAP-endorses-new-recommendations-on-sleep-times) / [AASM study (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4877308/) | Total sleep recommendations (4mo+), sleep training age guidance |
| **National Sleep Foundation** - [How Much Sleep Do You Need](https://www.thensf.org/how-many-hours-of-sleep-do-you-really-need/) | Total sleep recommendations (all ages including 0-3mo) |
| **CDC** - [About Sleep](https://www.cdc.gov/sleep/about/index.html) | Total sleep ranges |
| **WHO** - [24-Hour Movement Guidelines](https://www.who.int/publications-detail-redirect/9789241550536) | Total sleep for infants and toddlers |
| **Cleveland Clinic** - [Wake Windows by Age](https://health.clevelandclinic.org/wake-windows-by-age) / [Sleep Training](https://health.clevelandclinic.org/when-and-how-to-sleep-train-your-baby) | Wake window ranges (primary source), sleep training readiness |
| **Mayo Clinic** - [Baby Sleep](https://www.mayoclinic.org/healthy-lifestyle/infant-and-toddler-health/in-depth/baby-sleep/art-20045014) / [Baby Naps](https://www.mayoclinic.org/healthy-lifestyle/infant-and-toddler-health/in-depth/baby-naps/art-20047421) | Night sleep consolidation milestones, nap guidance |
| **Stanford Children's Health** - [Infant Sleep](https://www.stanfordchildrens.org/en/topic/default?id=infant-sleep-90-P02237) | Newborn sleep patterns, total sleep |
| **Sleep Foundation** - [Baby Sleep Needs](https://www.sleepfoundation.org/children-and-sleep/how-much-sleep-do-kids-need) / [Room Temperature](https://www.sleepfoundation.org/baby-sleep/best-room-temperature-for-sleeping-baby) | Nap counts, daytime sleep, sleep regressions, bedtime ranges, room temp |

### Data Point Summary

#### Total Sleep Per Day
| Age | Hours | Sources |
|-----|-------|---------|
| 0-3 months | 14-17 | NSF, WHO, CDC. AAP/AASM has no recommendation for <4mo |
| 3-6 months | 12-16 | AAP/AASM, CDC, WHO, Cleveland Clinic |
| 6-12 months | 12-16 (typically 13-14) | AAP/AASM, Sleep Foundation |
| 12-24 months | 11-14 | AAP/AASM, NSF, CDC |

#### Wake Windows (Cleveland Clinic)
| Age | Range |
|-----|-------|
| 0-1 month | 30-60 min |
| 2-3 months | 1-2 hours |
| 4-5 months | 1.25-2.5 hours |
| 6-7 months | 2-4 hours |
| 8-9 months | 2.5-4.5 hours |
| 10-12 months | 3-4 hours |
| 13-18 months | 3-5.5 hours |
| 19-24 months | 4-6 hours |
| 25-36 months | 5-6 hours |

#### Typical Bedtimes (Sleep Foundation)
| Age | Range |
|-----|-------|
| 0-3 months | 8:00-11:00 PM (no circadian rhythm yet) |
| 4-6 months | 7:00-8:30 PM |
| 7-12 months | 6:30-8:00 PM |
| 13-24 months | 7:00-8:00 PM |
| 25-36 months | 7:00-8:30 PM |

#### Alert Thresholds
| Sensor | Threshold | Source |
|--------|-----------|--------|
| Temperature | < 18°C or > 26°C | Sleep Foundation, CDC (20-22°C optimal) |
| Humidity | < 30% or > 60% | Pediatric guidelines |
| Noise | > 50 dB | Hugh et al. 2014 (50 dBA max recommended for nurseries) |

#### Room Temperature
| Value | Sources |
|-------|---------|
| 68-72°F (20-22°C) optimal | Sleep Foundation, CDC. AAP identifies overheating as SIDS risk factor |

#### Sleep Regressions
| Age | Cause | Sources |
|-----|-------|---------|
| 4 months | Permanent sleep cycle reorganization | Sleep Foundation, medical consensus |
| 8 months | Crawling, standing, separation anxiety | Sleep Foundation, Cleveland Clinic |
| 12 months | Walking milestone (~55% of toddlers) | Sleep Foundation |
| 18 months | Language explosion, autonomy, molars (3-6 weeks) | Sleep Foundation |

#### Sleep Training
| Guideline | Sources |
|-----------|---------|
| Not appropriate before 4 months | AAP, Cleveland Clinic |
| Can begin at 4-6 months | AAP, Cleveland Clinic, Sleep Foundation |
| Most effective before 8 months | Cleveland Clinic |
