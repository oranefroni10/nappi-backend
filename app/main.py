"""FastAPI app — lifespan, CORS, router registration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from .api.endpoints import router
from .api.auth import router as auth_router
from .api.sensor_events import router as sensor_router
from .api.stats import router as stats_router
from .api.alerts import router as alerts_router, push_router
from .api.babies import router as babies_router
from .api.chat import router as chat_router
from .services.scheduler import start_scheduler, stop_scheduler
from .core.database import get_database
from .core.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# Used by: FastAPI lifespan — init DB + scheduler on startup, tear down on shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_database()
    await db.connect(settings.DATABASE_URL)
    await start_scheduler()
    
    yield
    
    await stop_scheduler()
    await db.disconnect()


app = FastAPI(
    title="Baby Monitor API",
    version="3.0.0",
    description="Nappi - Baby Sleep Monitoring API",
    lifespan=lifespan
)

cors_origins = settings.CORS_ORIGINS.copy()
if settings.CORS_EXTRA_ORIGINS:
    cors_origins.extend([o.strip() for o in settings.CORS_EXTRA_ORIGINS.split(",") if o.strip()])

def allow_origin(origin: str) -> bool:
    """Also allows all Vercel preview URLs."""
    if origin in cors_origins:
        return True
    if origin.endswith(".vercel.app"):
        return True
    return False

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router, tags=["monitoring"])
app.include_router(sensor_router)
app.include_router(stats_router)
app.include_router(alerts_router)
app.include_router(push_router)
app.include_router(babies_router)
app.include_router(chat_router)
