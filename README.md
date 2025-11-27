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
- [Development](#development)
- [Current Status](#current-status)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Project Overview

**Nappi** is a baby monitoring system that:
- Tracks sleep patterns and quality
- Monitors room environment (temperature, humidity, noise, light)
- Collects data from IoT sensors
- Provides REST API for frontend applications
- Runs background tasks for continuous monitoring

**Current Phase**: Sprint 1 - MVP Skeleton

---

## 🛠️ Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) - Modern, fast web framework
- **Database**: PostgreSQL with [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (async)
- **Async Runtime**: Python's `asyncio`
- **Background Jobs**: [APScheduler](https://apscheduler.readthedocs.io/)
- **HTTP Client**: [aiohttp](https://docs.aiohttp.org/)
- **Data Validation**: [Pydantic](https://docs.pydantic.dev/) v2

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI application entry point
│   │
│   ├── api/                     # API Layer
│   │   ├── endpoints.py        # REST API routes
│   │   └── models.py           # Pydantic request/response models
│   │
│   ├── core/                    # Core Infrastructure
│   │   ├── database.py         # Database connection manager
│   │   └── utils.py            # Configuration and constants
│   │
│   └── services/                # Background Services
│       ├── data_miner.py       # Sensor data collection
│       ├── scheduler.py        # Task scheduler
│       └── tasks.py            # Background tasks
│
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

### Key Files Explained

| File | Purpose |
|------|---------|
| `main.py` | Application initialization, middleware, lifespan events |
| `api/endpoints.py` | REST API route definitions |
| `api/models.py` | Pydantic schemas for API requests/responses |
| `core/database.py` | Singleton database manager with connection pooling |
| `core/utils.py` | Configuration and environment variables |
| `services/data_miner.py` | HTTP client for fetching sensor data |
| `services/scheduler.py` | APScheduler setup and management |
| `services/tasks.py` | Background task implementations |

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

# Logging
LOG_LEVEL=INFO
```

---

## ⚙️ Configuration

Configuration is managed in `app/core/utils.py` and loaded from environment variables.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/nappi` | PostgreSQL connection string |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `SENSOR_API_BASE_URL` | `http://localhost:8000` | Base URL for sensor API |
| `SENSOR_POLL_INTERVAL_SECONDS` | `5` | How often to poll sensors (seconds) |
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
- [x] Background task scheduler
- [x] Sensor data collection (HTTP polling)
- [x] CORS middleware for frontend
- [x] Mock API endpoints for sleep and room data
- [x] Proper application lifecycle (startup/shutdown)
- [x] Logging infrastructure

### 🚧 In Progress / TODO

- [ ] **Database Integration**: ORM models and data persistence
- [ ] **Real Endpoints**: Connect endpoints to database queries
- [ ] **Store Sensor Data**: Save collected sensor data to database
- [ ] **Sleep Tracking Logic**: Implement actual sleep analysis
- [ ] **Authentication**: Add JWT-based authentication
- [ ] **Health Check Endpoint**: Add `/health` endpoint
- [ ] **Database Migrations**: Setup Alembic
- [ ] **Testing**: Unit and integration tests
- [ ] **Docker**: Containerization
- [ ] **CI/CD**: Automated testing and deployment

### ⚠️ Known Issues

1. **Mock Data Only**: Endpoints return hardcoded data, not from database
2. **Deprecated datetime**: Using `datetime.utcnow()` (deprecated in Python 3.12+)
3. **Sensor Data Not Stored**: Collected data is logged but not persisted
4. **No Authentication**: API is open to all requests
5. **Sensor API Configuration**: Default points to same host (needs external sensor API)

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

---

## 👥 Contributing

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes
3. Test thoroughly
4. Commit with clear messages: `git commit -m "Add: feature description"`
5. Push and create a Pull Request

---

## 📝 Notes for Team

- **Baby Name**: Currently hardcoded as "Noa" - will be dynamic in future sprints
- **Environment**: Always use virtual environment for dependencies
- **Database**: Each developer should have their own local PostgreSQL database
- **Sensors**: For development, you can mock sensor responses or use a test sensor API
- **Logs**: Check console output for scheduler activity and sensor polling

---

## 📞 Support

For questions or issues, contact the project maintainers or create an issue in the repository.

**Happy Coding! 👶💤**

