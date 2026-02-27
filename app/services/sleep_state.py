"""In-memory state for tracking which babies are asleep. Cooldowns ignore sensor events after parent override."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from app.core.constants import INTERVENTION_COOLDOWN_MINUTES

logger = logging.getLogger(__name__)


@dataclass
class SleepSession:
    baby_id: int
    start_time: datetime


class SleepStateManager:
    """Tracks sleeping babies; cooldowns ignore sensor events after parent override."""

    def __init__(self):
        self._sleeping_babies: Dict[int, SleepSession] = {}
        self._intervention_cooldowns: Dict[int, datetime] = {}  # baby_id -> cooldown_until
        self._lock = asyncio.Lock()
    
    # Used by: sensor_events.py — sleep-start endpoint, parent override
    async def start_sleep(self, baby_id: int) -> SleepSession:
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
    
    # Used by: sensor_events.py — sleep-end endpoint, parent override
    async def end_sleep(self, baby_id: int) -> Optional[SleepSession]:
        async with self._lock:
            session = self._sleeping_babies.pop(baby_id, None)
            if session is None:
                logger.warning(f"Baby {baby_id} was not marked as sleeping")
                return None
            
            logger.info(
                f"Baby {baby_id} woke up after sleeping since {session.start_time}"
            )
            return session
    
    # Used by: tasks.py (sensor polling), sensor_events.py (list sleeping babies)
    async def get_sleeping_babies(self) -> List[int]:
        async with self._lock:
            return list(self._sleeping_babies.keys())
    
    # Used by: sensor_events.py — get sleep status endpoint
    async def get_sleep_session(self, baby_id: int) -> Optional[SleepSession]:
        async with self._lock:
            return self._sleeping_babies.get(baby_id)
    
    # Used by: (not currently called externally)
    async def is_sleeping(self, baby_id: int) -> bool:
        async with self._lock:
            return baby_id in self._sleeping_babies
    
    # Used by: (internal utility)
    async def get_sleep_count(self) -> int:
        async with self._lock:
            return len(self._sleeping_babies)
    
    # Used by: sensor_events.py — parent override endpoint
    async def start_intervention_cooldown(self, baby_id: int) -> datetime:
        async with self._lock:
            cooldown_until = datetime.utcnow() + timedelta(minutes=INTERVENTION_COOLDOWN_MINUTES)
            self._intervention_cooldowns[baby_id] = cooldown_until
            logger.info(
                f"Started intervention cooldown for baby {baby_id}, "
                f"expires at {cooldown_until} ({INTERVENTION_COOLDOWN_MINUTES} minutes)"
            )
            return cooldown_until
    
    # Used by: sensor_events.py — sleep-start/end cooldown guard, cooldown status endpoint
    async def is_in_cooldown(self, baby_id: int) -> bool:
        async with self._lock:
            cooldown_until = self._intervention_cooldowns.get(baby_id)
            if cooldown_until is None:
                return False
            
            if datetime.utcnow() < cooldown_until:
                return True
            
            del self._intervention_cooldowns[baby_id]
            logger.info(f"Intervention cooldown expired for baby {baby_id}")
            return False
    
    # Used by: sensor_events.py — cooldown guard response, cooldown status endpoint
    async def get_cooldown_remaining(self, baby_id: int) -> Optional[int]:
        async with self._lock:
            cooldown_until = self._intervention_cooldowns.get(baby_id)
            if cooldown_until is None:
                return None
            
            remaining = (cooldown_until - datetime.utcnow()).total_seconds() / 60.0
            if remaining > 0:
                return int(remaining) + 1  # Round up
            
            del self._intervention_cooldowns[baby_id]
            return None
    
    # Used by: (internal utility)
    async def clear_cooldown(self, baby_id: int) -> bool:
        async with self._lock:
            if baby_id in self._intervention_cooldowns:
                del self._intervention_cooldowns[baby_id]
                logger.info(f"Cleared intervention cooldown for baby {baby_id}")
                return True
            return False


_sleep_state_manager: Optional[SleepStateManager] = None


# Used by: sensor_events.py, tasks.py (sensor polling scheduler)
def get_sleep_state_manager() -> SleepStateManager:
    global _sleep_state_manager
    if _sleep_state_manager is None:
        _sleep_state_manager = SleepStateManager()
    return _sleep_state_manager
