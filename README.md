# 👶 Nappi Baby Monitor API

Backend API for baby sleep and room monitoring system. This FastAPI application tracks sleep patterns, monitors room conditions, and collects data from various sensors.

---

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Smart Features](#smart-features)
- [Statistics Page Guide](#-statistics-page-guide)
- [Database Tables](#database-tables)
- [Scheduled Jobs](#scheduled-jobs)
- [Development](#development)
- [Current Status](#current-status)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Project Overview

**Nappi** is a baby monitoring system that:
- Tracks sleep patterns and quality
- Monitors room environment (temperature, humidity, noise, light)
- Collects data from IoT sensors (M5 devices)
- Analyzes awakening correlations with AI-powered insights
- Learns optimal sleep conditions for each baby
- Provides REST API for frontend applications
- Runs background tasks for continuous monitoring

**Current Phase**: Sprint 2 - Smart Features

---

## 🛠️ Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) - Modern, fast web framework
- **Database**: PostgreSQL with [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (async)
- **Async Runtime**: Python's `asyncio`
- **Background Jobs**: [APScheduler](https://apscheduler.readthedocs.io/)
- **HTTP Client**: [aiohttp](https://docs.aiohttp.org/)
- **Data Validation**: [Pydantic](https://docs.pydantic.dev/) v2
- **AI Insights**: [Google Gemini](https://ai.google.dev/) - For awakening correlation analysis

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI application entry point
│   │
│   ├── api/                     # API Layer
│   │   ├── endpoints.py         # REST API routes (monitoring)
│   │   ├── sensor_events.py     # Sensor event endpoints (sleep start/end)
│   │   ├── auth.py              # Authentication routes
│   │   └── models.py            # Pydantic request/response models
│   │
│   ├── core/                    # Core Infrastructure
│   │   ├── database.py          # Database connection manager
│   │   ├── settings.py          # Configuration settings
│   │   └── utils.py             # Constants and utilities
│   │
│   ├── db/                      # Database Layer
│   │   ├── models.py            # Pydantic models for DB tables
│   │   └── generate_models.py   # Script to generate models from DB
│   │
│   └── services/                # Background Services
│       ├── scheduler.py         # Task scheduler (APScheduler)
│       ├── tasks.py             # Sensor collection tasks
│       ├── data_miner.py        # HTTP client for sensors
│       ├── babies_data.py       # Database operations
│       ├── sleep_state.py       # In-memory sleep state tracking
│       ├── correlation_analyzer.py  # Awakening correlation analysis
│       ├── daily_summary.py     # Daily summary generation
│       ├── optimal_stats.py     # Optimal conditions calculator
│       └── sleep_patterns.py    # Sleep pattern clustering algorithm
│
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

### Key Files Explained

| File | Purpose |
|------|---------|
| `main.py` | Application initialization, middleware, lifespan events |
| `api/endpoints.py` | REST API route definitions (monitoring) |
| `api/sensor_events.py` | M5 sensor event handlers (sleep start/end/away) |
| `api/models.py` | Pydantic schemas for API requests/responses |
| `core/database.py` | Singleton database manager with connection pooling |
| `core/settings.py` | Configuration settings and environment variables |
| `services/scheduler.py` | APScheduler setup and job management |
| `services/tasks.py` | Sensor data collection task |
| `services/babies_data.py` | Database operations for babies and sleep data |
| `services/sleep_state.py` | In-memory tracking of which babies are sleeping |
| `services/correlation_analyzer.py` | Analyzes sensor changes before awakenings |
| `services/daily_summary.py` | Daily aggregation and cleanup |
| `services/optimal_stats.py` | Calculates optimal sleep conditions |
| `services/sleep_patterns.py` | Clusters sleep sessions to find typical patterns |
| `api/stats.py` | Statistics page API endpoints |

---

## 🚀 Getting Started

### Prerequisites

- **Python**: 3.10 or higher
- **PostgreSQL**: 13 or higher
- **pip**: Latest version

### 1. Clone the Repository

```bash
git clone <repository-url>
cd nappi-project/backend
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Setup Database

```bash
# Create PostgreSQL database
createdb nappi

# Or using psql:
psql -U postgres
CREATE DATABASE nappi;
\q
```

### 5. Configure Environment

Create a `.env` file in the `backend/` directory:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/nappi

# Server
HOST=0.0.0.0
PORT=8000

# Sensors
SENSOR_API_BASE_URL=http://your-sensor-device:8080
SENSOR_POLL_INTERVAL_SECONDS=5

# AI Insights (optional - get key from https://ai.google.dev/)
GEMINI_API_KEY=your_gemini_api_key

# Correlation Analysis
CORRELATION_CHANGE_THRESHOLD_PERCENT=10
CORRELATION_TIME_WINDOW_MINUTES=60

# Daily Jobs (Israel timezone)
DAILY_SUMMARY_HOUR=10
DAILY_SUMMARY_TIMEZONE=Asia/Jerusalem

# Logging
LOG_LEVEL=INFO
```

---

## ⚙️ Configuration

Configuration is managed in `app/core/utils.py` and loaded from environment variables.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | PostgreSQL connection string |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `SENSOR_API_BASE_URL` | `http://localhost:8001` | Base URL for sensor hub |
| `SENSOR_POLL_INTERVAL_SECONDS` | `5` | How often to poll sensors (seconds) |
| `GEMINI_API_KEY` | - | Google Gemini API key for AI insights |
| `CORRELATION_CHANGE_THRESHOLD_PERCENT` | `10` | Min % change to flag as significant |
| `CORRELATION_TIME_WINDOW_MINUTES` | `60` | Time window to analyze before awakening |
| `DAILY_SUMMARY_HOUR` | `10` | Hour to run daily jobs (24h format) |
| `DAILY_SUMMARY_TIMEZONE` | `Asia/Jerusalem` | Timezone for daily jobs |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Sensor Configuration

Sensors are defined in `app/core/utils.py`:

```python
SENSOR_TO_ENDPOINT_MAP = {
    "temperature": "/temperature",
    "humidity": "/humidity",
    "pressure": "/pressure",
    "camera": "/camera"
}
```

---

## 🏃 Running the Application

### Development Mode (with auto-reload)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Access the Application

- **API**: http://localhost:8000
- **Interactive API Docs**: http://localhost:8000/docs
- **Alternative API Docs**: http://localhost:8000/redoc

---

## 📡 API Endpoints

### Health & Status

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| `GET` | `/docs` | Interactive API documentation | ✅ Built-in |
| `GET` | `/redoc` | Alternative API documentation | ✅ Built-in |

### Sensor Events (M5 sensors call these)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sensor/sleep-start` | Baby fell asleep → start collecting sensor data |
| `POST` | `/sensor/sleep-end` | Baby woke up → stop collecting, save event, run AI analysis |
| `POST` | `/sensor/baby-away` | Baby left crib → stop collecting (no awakening event) |
| `GET` | `/sensor/sleep-status/{id}` | Check if specific baby is sleeping |
| `GET` | `/sensor/sleeping-babies` | List all currently sleeping babies |

### Sleep Monitoring

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| `GET` | `/sleep/latest` | Get last sleep summary | ✅ Mock Data |

**Response Example:**
```json
{
  "baby_name": "Noa",
  "started_at": "2025-11-27T00:00:00Z",
  "ended_at": "2025-11-27T08:00:00Z",
  "total_sleep_minutes": 480,
  "awakenings_count": 2,
  "sleep_quality_score": 87,
  "stages": [
    {
      "stage": "light",
      "start_time": "2025-11-27T00:00:00Z",
      "end_time": "2025-11-27T01:30:00Z"
    }
  ]
}
```

### Room Monitoring

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| `GET` | `/room/current` | Get current room metrics | ✅ Mock Data |

**Response Example:**
```json
{
  "temperature_c": 22.7,
  "humidity_percent": 47.0,
  "noise_db": 32.5,
  "light_lux": 15.0,
  "measured_at": "2025-11-27T12:00:00Z",
  "notes": "Room is quiet and slightly dark."
}
```

### Statistics Page

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/stats/sensors` | Sensor averages over time (for graphs) |
| `GET` | `/stats/sleep-patterns` | Sleep time patterns with clustering |
| `GET` | `/stats/daily-sleep` | Daily sleep totals over time |

See [Statistics Page Guide](#-statistics-page-guide) below for detailed examples.

---

## 🧠 Smart Features

### 1. Correlation Analysis
**When:** Triggered every time a baby wakes up

- Looks at the last 60 minutes of sensor data before awakening
- Compares first 25% of readings vs last 25% of readings
- Calculates percentage change for each sensor (temp, humidity, noise, heart rate)
- Only keeps changes ≥10% (significant changes)
- **Stored in:** `correlations.parameters`

### 2. Gemini AI Insights
**When:** Right after correlation analysis

- Sends significant sensor changes to Google Gemini AI
- AI analyzes what likely caused the awakening
- Returns 2-3 sentence explanation with actionable advice for parents
- **Stored in:** `correlations.extra_data`

### 3. Optimal Conditions Calculator
**When:** Daily at 10:05 AM

- Looks at ALL historical daily summaries for each baby
- Gives each day a weight based on sleep quality (fewer awakenings = higher weight)
- Calculates weighted average for temperature, humidity, and noise
- Result = conditions that historically worked best for that baby
- **Stored in:** `optimal_stats` (one row per baby, updated daily)

**Formula:**
```
weight = 1 / (1 + total_awakenings)

optimal_value = Σ(value × weight) / Σ(weight)
```

**Example:**
| Day | Temp | Awakenings | Weight | Temp × Weight |
|-----|------|------------|--------|---------------|
| Mon | 22°C | 0 | 1.00 | 22.00 |
| Tue | 25°C | 2 | 0.33 | 8.25 |
| Wed | 23°C | 1 | 0.50 | 11.50 |
| **Sum** | | | **1.83** | **41.75** |
| **Optimal** | **22.8°C** | | | 41.75 ÷ 1.83 |

---

## 📊 Statistics Page Guide

The Statistics page provides three types of data for graphs. Here's how each one works:

### 1. Sensor Data Over Time (`/stats/sensors`)

Returns daily sensor averages for graphing trends over weeks or months.

**Request:**
```
GET /stats/sensors?baby_id=1&sensor=temperature&start_date=2026-01-01&end_date=2026-01-14
```

**What it does:**
- Fetches data from `daily_summary` table
- Returns one data point per day (daily average)
- Supports: `temperature`, `humidity`, `noise`

**Response:**
```json
{
  "baby_id": 1,
  "sensor": "temperature",
  "data": [
    {"date": "2026-01-01", "value": 22.5},
    {"date": "2026-01-02", "value": 23.1},
    {"date": "2026-01-03", "value": 21.8}
  ]
}
```

**Note:** These are averages of sensor readings *during sleep only*, not 24/7 room data.

---

### 2. Sleep Patterns (`/stats/sleep-patterns`)

Helps parents know **when their baby typically sleeps**. Perfect for planning or telling a babysitter the baby's schedule.

**Request:**
```
GET /stats/sleep-patterns?baby_id=1&month=1&year=2026
```

#### How the Calculation Works (Simple Example)

Let's say during January, the baby had these sleep sessions:

| Session | Start Time | End Time |
|---------|------------|----------|
| 1 | 8:00 AM | 9:30 AM |
| 2 | 8:15 AM | 11:00 AM |
| 3 | 10:00 AM | 12:00 PM |
| 4 | 2:00 PM | 4:00 PM |
| 5 | 2:30 PM | 4:30 PM |
| 6 | 8:00 PM | 6:00 AM |
| 7 | 8:30 PM | 6:30 AM |

**Step 1: Group by Start Time**

The algorithm sorts sessions by start time and creates a **new group when there's a gap > 2 hours**.

```
Group 1: [8:00, 8:15, 10:00] → Morning naps (gap between them < 2 hours)
Group 2: [14:00, 14:30]     → Afternoon naps (gap from 10:00 is 4 hours → new group)
Group 3: [20:00, 20:30]     → Night sleep (gap from 14:30 is 5.5 hours → new group)
```

**Step 2: Calculate Averages for Each Group**

For **Morning naps** (sessions 1, 2, 3):
```
Average start = (8:00 + 8:15 + 10:00) ÷ 3 = 8:45 AM
Average end   = (9:30 + 11:00 + 12:00) ÷ 3 = 10:50 AM
```

For **Afternoon naps** (sessions 4, 5):
```
Average start = (14:00 + 14:30) ÷ 2 = 14:15 (2:15 PM)
Average end   = (16:00 + 16:30) ÷ 2 = 16:15 (4:15 PM)
```

For **Night sleep** (sessions 6, 7):
```
Average start = (20:00 + 20:30) ÷ 2 = 20:15 (8:15 PM)
Average end   = (6:00 + 6:30) ÷ 2   = 6:15 AM
```

**Response:**
```json
{
  "baby_id": 1,
  "month": 1,
  "year": 2026,
  "total_sessions": 7,
  "patterns": [
    {
      "cluster_id": 1,
      "label": "Morning nap",
      "avg_start": "08:45",
      "avg_end": "10:50",
      "avg_duration_hours": 2.08,
      "session_count": 3,
      "earliest_start": "08:00",
      "latest_end": "12:00"
    },
    {
      "cluster_id": 2,
      "label": "Afternoon nap",
      "avg_start": "14:15",
      "avg_end": "16:15",
      "avg_duration_hours": 2.0,
      "session_count": 2,
      "earliest_start": "14:00",
      "latest_end": "16:30"
    },
    {
      "cluster_id": 3,
      "label": "Night sleep",
      "avg_start": "20:15",
      "avg_end": "06:15",
      "avg_duration_hours": 10.0,
      "session_count": 2,
      "earliest_start": "20:00",
      "latest_end": "06:30"
    }
  ]
}
```

**What Parents See:**
> "Your baby typically sleeps:
> - Morning nap: 8:45 AM - 10:50 AM
> - Afternoon nap: 2:15 PM - 4:15 PM  
> - Night: 8:15 PM - 6:15 AM"

---

### 3. Daily Sleep Totals (`/stats/daily-sleep`)

Shows **how much total sleep** the baby got each day. Great for tracking sleep trends over time.

**Request:**
```
GET /stats/daily-sleep?baby_id=1&start_date=2026-01-01&end_date=2026-01-07
```

**What it does:**
- Sums up all sleep session durations for each day
- Counts how many sleep sessions occurred

**Example Calculation:**

On January 5th, baby had 3 sleep sessions:
- Morning nap: 90 minutes
- Afternoon nap: 60 minutes  
- Night sleep: 540 minutes (9 hours)

```
Total = 90 + 60 + 540 = 690 minutes = 11.5 hours
```

**Response:**
```json
{
  "baby_id": 1,
  "data": [
    {"date": "2026-01-05", "total_hours": 11.5, "sessions_count": 3},
    {"date": "2026-01-06", "total_hours": 13.2, "sessions_count": 4},
    {"date": "2026-01-07", "total_hours": 12.0, "sessions_count": 3}
  ]
}
```

---

### Validation Rules

| Rule | Value |
|------|-------|
| Minimum date range | 7 days |
| Maximum date range | 90 days (3 months) |
| Baby must exist | Returns 404 if not found |

---

## 🗄️ Database Tables

| Table | Purpose |
|-------|---------|
| `users` | User accounts |
| `babies` | Baby profiles |
| `sleep_realtime_data` | Raw sensor readings (deleted daily after summary) |
| `awakening_events` | When baby woke up + metadata |
| `correlations` | What changed before awakening + AI insights |
| `daily_summary` | Daily averages + morning/noon/night awakening counts |
| `optimal_stats` | Best conditions per baby (one row each, updated daily) |

### Awakening Time Periods

- **Morning** — 6am to 12pm
- **Noon** — 12pm to 6pm
- **Night** — 6pm to 6am

---

## ⏰ Scheduled Jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| **Sensor Collection** | Every 5 seconds | Collects data for sleeping babies only |
| **Daily Summary** | 10:00 AM Israel | Generates summaries, cleans up raw data |
| **Optimal Stats** | 10:05 AM Israel | Calculates optimal conditions |

---

## 💻 Development

### Database Usage

The database manager is a singleton. Use it in your code:

```python
from app.core.database import get_database
from sqlalchemy import text

db = get_database()

# Use in async functions
async def my_function():
    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM room_metrics WHERE id = :id"),
            {"id": 1}
        )
        row = result.mappings().first()
        return row
```

### Adding New Endpoints

1. Define Pydantic model in `app/api/models.py`:
```python
class MyNewModel(BaseModel):
    field1: str
    field2: int
```

2. Add route in `app/api/endpoints.py`:
```python
@router.get("/my-endpoint", response_model=MyNewModel)
async def my_endpoint():
    return MyNewModel(field1="value", field2=42)
```

### Adding Background Tasks

1. Create task function in `app/services/tasks.py`:
```python
async def my_background_task():
    logger.info("Running my task...")
    # Your task logic here
```

2. Register in `app/services/scheduler.py`:
```python
scheduler.add_job(
    my_background_task,
    trigger=IntervalTrigger(seconds=60),
    id="my_task",
    name="My Background Task"
)
```

### Code Style

- Use `async`/`await` for all I/O operations
- Type hints are required for function signatures
- Use `logging` instead of `print()`
- Follow PEP 8 style guidelines

### Testing

```bash
# Run tests (when implemented)
pytest

# Run with coverage
pytest --cov=app tests/
```

---

## 📊 Current Status

### ✅ Implemented

- [x] FastAPI application structure
- [x] Async database connection manager
- [x] Background task scheduler (APScheduler)
- [x] Sensor data collection (HTTP polling)
- [x] CORS middleware for frontend
- [x] Proper application lifecycle (startup/shutdown)
- [x] Logging infrastructure
- [x] **Sleep state tracking** (in-memory, event-driven)
- [x] **M5 sensor endpoints** (sleep-start, sleep-end, baby-away)
- [x] **Awakening events** recording with metadata
- [x] **Correlation analysis** (sensor change detection)
- [x] **Gemini AI integration** for insights
- [x] **Daily summary generation** with awakening counts
- [x] **Optimal stats calculation** with weighted averages
- [x] **Database operations** for all features
- [x] **Statistics page endpoints** (sensors, sleep patterns, daily sleep)
- [x] **Sleep pattern clustering** with averaged time windows

### 🚧 In Progress / TODO

- [ ] **Authentication**: Add JWT-based authentication
- [ ] **Health Check Endpoint**: Add `/health` endpoint
- [ ] **Database Migrations**: Setup Alembic
- [ ] **Testing**: Unit and integration tests
- [ ] **Docker**: Containerization
- [ ] **CI/CD**: Automated testing and deployment

### ⚠️ Known Issues

1. **No Authentication**: API is open to all requests (sensor endpoints don't require auth)
2. **Gemini Rate Limits**: Free tier has quota limits, system falls back gracefully
3. **SSL on macOS**: May need to install certificates (`pip install certifi`)

---

## 🐛 Troubleshooting

### Issue: Cannot connect to database

**Error**: `connection refused` or `database does not exist`

**Solution**:
```bash
# Ensure PostgreSQL is running
pg_ctl status

# Create database if missing
createdb nappi

# Check connection string in .env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/nappi
```

### Issue: Module import errors

**Error**: `ModuleNotFoundError: No module named 'fastapi'`

**Solution**:
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue: Scheduler not running

**Error**: Sensor data not being collected

**Solution**:
1. Check logs for scheduler initialization
2. Verify `SENSOR_API_BASE_URL` is correct
3. Ensure external sensor API is running and accessible
4. Check that baby is marked as "sleeping" via `/sensor/sleep-start`

### Issue: Gemini API errors

**Error**: `429 Rate Limit` or `SSL Certificate errors`

**Solution**:
```bash
# For SSL errors on macOS
pip install certifi

# For rate limits - the system automatically tries fallback models
# Check logs for: "Rate limit on [model], trying next model..."
# If all models exhausted, correlation is still saved without AI insights
```

### Issue: CORS errors from frontend

**Error**: `CORS policy: No 'Access-Control-Allow-Origin' header`

**Solution**:
Add your frontend URL to `CORS_ORIGINS` in `app/core/utils.py`:
```python
CORS_ORIGINS: list = [
    "http://localhost:5173",    # Vite default
    "http://localhost:3000",    # React/Next.js default
    "http://your-frontend-url",  # Add your URL here
]
```

---

## 📚 Additional Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **SQLAlchemy Async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **APScheduler**: https://apscheduler.readthedocs.io/en/3.x/
- **Pydantic**: https://docs.pydantic.dev/latest/
- **Google Gemini API**: https://ai.google.dev/

---

## 👥 Contributing

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes
3. Test thoroughly
4. Commit with clear messages: `git commit -m "Add: feature description"`
5. Push and create a Pull Request

---

## 📝 Notes for Team

- **Environment**: Always use virtual environment for dependencies
- **Database**: Each developer should have their own local PostgreSQL database
- **Sensors**: Use the mock sensor hub at `mock_sensor_data/` for development
- **Gemini API**: Get a free API key from https://ai.google.dev/ (optional, system works without it)
- **Logs**: Check console output for scheduler activity and sensor polling
- **Daily Jobs**: Run at 10:00 AM Israel time - adjust `DAILY_SUMMARY_HOUR` if needed

---

## 📞 Support

For questions or issues, contact the project maintainers or create an issue in the repository.

**Happy Coding! 👶💤**

