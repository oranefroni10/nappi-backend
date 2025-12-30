"""
Sleep State Manager - Tracks which babies are currently asleep.

This module provides an in-memory state manager for tracking sleep sessions.
The M5 sensors report sleep start/end events, and the scheduler uses this
to only collect sensor data for sleeping babies.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SleepSession:
    """Represents an active sleep session for a baby."""
    baby_id: int
    start_time: datetime


class SleepStateManager:
    """
    Thread-safe manager for tracking which babies are currently asleep.
    
    Uses an asyncio lock to ensure safe concurrent access from both
    the API endpoints and the scheduler.
    """
    
    def __init__(self):
        self._sleeping_babies: Dict[int, SleepSession] = {}
        self._lock = asyncio.Lock()
    
    async def start_sleep(self, baby_id: int) -> SleepSession:
        """
        Record that a baby has fallen asleep.
        
        Args:
            baby_id: The ID of the baby that fell asleep
            
        Returns:
            The created SleepSession
        """
        async with self._lock:
            if baby_id in self._sleeping_babies:
                logger.warning(
                    f"Baby {baby_id} already marked as sleeping since "
                    f"{self._sleeping_babies[baby_id].start_time}"
                )
                return self._sleeping_babies[baby_id]
            
            session = SleepSession(baby_id=baby_id, start_time=datetime.utcnow())
            self._sleeping_babies[baby_id] = session
            logger.info(f"Baby {baby_id} started sleeping at {session.start_time}")
            return session
    
    async def end_sleep(self, baby_id: int) -> Optional[SleepSession]:
        """
        Record that a baby has woken up.
        
        Args:
            baby_id: The ID of the baby that woke up
            
        Returns:
            The ended SleepSession if found, None if baby wasn't sleeping
        """
        async with self._lock:
            session = self._sleeping_babies.pop(baby_id, None)
            if session is None:
                logger.warning(f"Baby {baby_id} was not marked as sleeping")
                return None
            
            logger.info(
                f"Baby {baby_id} woke up after sleeping since {session.start_time}"
            )
            return session
    
    async def get_sleeping_babies(self) -> List[int]:
        """
        Get list of all currently sleeping baby IDs.
        
        Returns:
            List of baby IDs that are currently asleep
        """
        async with self._lock:
            return list(self._sleeping_babies.keys())
    
    async def get_sleep_session(self, baby_id: int) -> Optional[SleepSession]:
        """
        Get the sleep session for a specific baby.
        
        Args:
            baby_id: The ID of the baby to check
            
        Returns:
            The SleepSession if baby is sleeping, None otherwise
        """
        async with self._lock:
            return self._sleeping_babies.get(baby_id)
    
    async def is_sleeping(self, baby_id: int) -> bool:
        """
        Check if a specific baby is currently sleeping.
        
        Args:
            baby_id: The ID of the baby to check
            
        Returns:
            True if baby is sleeping, False otherwise
        """
        async with self._lock:
            return baby_id in self._sleeping_babies
    
    async def get_sleep_count(self) -> int:
        """
        Get the count of currently sleeping babies.
        
        Returns:
            Number of babies currently asleep
        """
        async with self._lock:
            return len(self._sleeping_babies)


# Global singleton instance
_sleep_state_manager: Optional[SleepStateManager] = None


def get_sleep_state_manager() -> SleepStateManager:
    """
    Get the global SleepStateManager singleton.
    
    Returns:
        The shared SleepStateManager instance
    """
    global _sleep_state_manager
    if _sleep_state_manager is None:
        _sleep_state_manager = SleepStateManager()
    return _sleep_state_manager

