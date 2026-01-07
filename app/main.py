from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from .api.endpoints import router
from .api.auth import router as auth_router
from .api.sensor_events import router as sensor_router
from .api.stats import router as stats_router
from .services.scheduler import start_scheduler, stop_scheduler
from .core.database import get_database
from .core.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db = get_database()
    await db.connect(settings.DATABASE_URL)
    await start_scheduler()
    
    yield
    
    # Shutdown
    await stop_scheduler()
    await db.disconnect()


app = FastAPI(
    title="Baby Monitor API",
    version="0.1.0",
    description="Backend for baby sleep & room monitoring (Sprint 1 skeleton).",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router, tags=["monitoring"])
app.include_router(sensor_router)
app.include_router(stats_router)

