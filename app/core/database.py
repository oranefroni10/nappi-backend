"""
Database Manager - Singleton for PostgreSQL connections.

USAGE EXAMPLE:
--------------

    from app.database import get_database
    from sqlalchemy import text

    db = get_database()

    # INSERT (session auto-closes when exiting 'async with' block)
    async with db.session() as session:
        await session.execute(
            text("INSERT INTO room_metrics (temperature_c, humidity_percent) VALUES (:temp, :humidity)"),
            {"temp": 22.5, "humidity": 45.0}
        )
        await session.commit()
    # ← session closed automatically here, no need to call close()

    # SELECT ONE
    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM room_metrics WHERE id = :id"),
            {"id": 1}
        )
        row = result.mappings().first()  # Returns dict or None

    # SELECT ALL
    async with db.session() as session:
        result = await session.execute(text("SELECT * FROM room_metrics ORDER BY measured_at DESC"))
        rows = result.mappings().all()  # Returns list of dicts

    # UPDATE
    async with db.session() as session:
        await session.execute(
            text("UPDATE room_metrics SET temperature_c = :temp WHERE id = :id"),
            {"temp": 23.0, "id": 1}
        )
        await session.commit()

    # DELETE
    async with db.session() as session:
        await session.execute(
            text("DELETE FROM room_metrics WHERE id = :id"),
            {"id": 1}
        )
        await session.commit()
"""

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class DatabaseManager:
    """
    Singleton that manages the database connection pool.
    
    Usage:
        db = get_database()
        await db.connect("postgresql+asyncpg://user:pass@localhost/nappi")
        
        async with db.session() as session:
            session.add(my_model)
            await session.commit()
    """
    
    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
    
    @property
    def is_connected(self) -> bool:
        return self._engine is not None
    
    async def connect(self, database_url: str) -> None:
        """Initialize the connection pool. Call once at startup."""
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
    
    async def disconnect(self) -> None:
        """Close the connection pool. Call once at shutdown."""
        if self._engine is None:
            return
        
        logger.info("Disconnecting from database...")
        await self._engine.dispose()
        self._engine = None
        self._session_factory = None
    
    def session(self) -> AsyncSession:
        """
        Get a session for database operations.
        
        Use as context manager:
            async with db.session() as session:
                result = await session.execute(select(User))
                await session.commit()
        """
        if self._session_factory is None:
            raise RuntimeError("Database not connected")
        return self._session_factory()


# Singleton
_db: Optional[DatabaseManager] = None


def get_database() -> DatabaseManager:
    """Get the database manager singleton."""
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db
