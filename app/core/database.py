"""Database singleton — async PostgreSQL connection pool via SQLAlchemy."""

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class DatabaseManager:
    """Manages the async connection pool. Call connect() once at startup."""
    
    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
    
    @property
    def is_connected(self) -> bool:
        return self._engine is not None
    
    # Used by: main.py lifespan (startup)
    async def connect(self, database_url: str) -> None:
        if self._engine is not None:
            logger.warning("Database already connected")
            return
        
        logger.info(f"Connecting to database...")
        
        self._engine = create_async_engine(database_url, echo=False)
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        logger.info("Database connected")
    
    # Used by: main.py lifespan (shutdown)
    async def disconnect(self) -> None:
        if self._engine is None:
            return
        
        logger.info("Disconnecting from database...")
        await self._engine.dispose()
        self._engine = None
        self._session_factory = None
    
    # Used by: all services/endpoints that need DB access
    def session(self) -> AsyncSession:
        """Use as: async with db.session() as session: ..."""
        if self._session_factory is None:
            raise RuntimeError("Database not connected")
        return self._session_factory()


_db: Optional[DatabaseManager] = None


def get_database() -> DatabaseManager:
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db
