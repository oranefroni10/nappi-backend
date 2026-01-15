"""
Sleep State Manager - Tracks which babies are currently asleep.

This module provides an in-memory state manager for tracking sleep sessions.
The M5 sensors report sleep start/end events, and the scheduler uses this
to only collect sensor data for sleeping babies.

Also manages intervention cooldowns - when a parent manually overrides the
sleep state, sensor events are ignored for a configurable period.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Intervention cooldown duration in minutes
INTERVENTION_COOLDOWN_MINUTES = 20


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
    
    Also manages intervention cooldowns - after a parent manually overrides
    the sleep state, sensor events are ignored for INTERVENTION_COOLDOWN_MINUTES.
    """
    
    def __init__(self):
        self._sleeping_babies: Dict[int, SleepSession] = {}
        self._intervention_cooldowns: Dict[int, datetime] = {}  # baby_id -> cooldown_until
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
    
    # ============================================
    # Intervention Cooldown Methods
    # ============================================
    
    async def start_intervention_cooldown(self, baby_id: int) -> datetime:
        """
        Start an intervention cooldown period for a baby.
        
        During the cooldown, sensor sleep/awake events will be ignored.
        This prevents the sensor from immediately overriding a parent's
        manual intervention.
        
        Args:
            baby_id: The ID of the baby
            
        Returns:
            The datetime when the cooldown expires
        """
        async with self._lock:
            cooldown_until = datetime.utcnow() + timedelta(minutes=INTERVENTION_COOLDOWN_MINUTES)
            self._intervention_cooldowns[baby_id] = cooldown_until
            logger.info(
                f"Started intervention cooldown for baby {baby_id}, "
                f"expires at {cooldown_until} ({INTERVENTION_COOLDOWN_MINUTES} minutes)"
            )
            return cooldown_until
    
    async def is_in_cooldown(self, baby_id: int) -> bool:
        """
        Check if a baby is in intervention cooldown.
        
        If in cooldown, sensor events should be ignored.
        
        Args:
            baby_id: The ID of the baby to check
            
        Returns:
            True if in cooldown (should ignore sensor events), False otherwise
        """
        async with self._lock:
            cooldown_until = self._intervention_cooldowns.get(baby_id)
            if cooldown_until is None:
                return False
            
            if datetime.utcnow() < cooldown_until:
                return True
            
            # Cooldown expired, clean up
            del self._intervention_cooldowns[baby_id]
            logger.info(f"Intervention cooldown expired for baby {baby_id}")
            return False
    
    async def get_cooldown_remaining(self, baby_id: int) -> Optional[int]:
        """
        Get the remaining cooldown time in minutes.
        
        Args:
            baby_id: The ID of the baby to check
            
        Returns:
            Remaining minutes if in cooldown, None otherwise
        """
        async with self._lock:
            cooldown_until = self._intervention_cooldowns.get(baby_id)
            if cooldown_until is None:
                return None
            
            remaining = (cooldown_until - datetime.utcnow()).total_seconds() / 60.0
            if remaining > 0:
                return int(remaining) + 1  # Round up
            
            # Cooldown expired
            del self._intervention_cooldowns[baby_id]
            return None
    
    async def clear_cooldown(self, baby_id: int) -> bool:
        """
        Clear the intervention cooldown for a baby (if any).
        
        Args:
            baby_id: The ID of the baby
            
        Returns:
            True if a cooldown was cleared, False if none existed
        """
        async with self._lock:
            if baby_id in self._intervention_cooldowns:
                del self._intervention_cooldowns[baby_id]
                logger.info(f"Cleared intervention cooldown for baby {baby_id}")
                return True
            return False


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

