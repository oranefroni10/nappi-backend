"""Handles Web Push notifications."""

import json
import logging
from typing import Optional, Dict, Any

from app.core.database import get_database
from app.core.settings import settings
from sqlalchemy import text

logger = logging.getLogger(__name__)


# Used by: alerts, alert_service
class PushService:
    def __init__(self):
        self.database = get_database()
        self._vapid_private_key: Optional[str] = None
        self._vapid_public_key: Optional[str] = None
        self._vapid_claims: Dict[str, str] = {}
        self._load_vapid_config()
    
    # Used by: __init__
    def _load_vapid_config(self):
        """Load VAPID config from environment."""
        self._vapid_private_key = getattr(settings, 'VAPID_PRIVATE_KEY', None)
        self._vapid_public_key = getattr(settings, 'VAPID_PUBLIC_KEY', None)
        vapid_email = getattr(settings, 'VAPID_EMAIL', 'admin@nappi.app')
        
        if self._vapid_private_key:
            self._vapid_claims = {
                "sub": f"mailto:{vapid_email}"
            }
            logger.info("VAPID configuration loaded")
        else:
            logger.warning(
                "VAPID keys not configured. Push notifications will not work. "
                "Generate keys with: npx web-push generate-vapid-keys"
            )
    
    # Used by: alerts, send_notification
    @property
    def is_configured(self) -> bool:
        """Whether push is configured."""
        return bool(self._vapid_private_key) and bool(self._vapid_public_key)
    
    # Used by: alerts
    @property
    def public_key(self) -> Optional[str]:
        """VAPID public key for client subscription."""
        return self._vapid_public_key
    
    # Used by: alerts
    async def save_subscription(
        self,
        user_id: int,
        endpoint: str,
        p256dh_key: str,
        auth_key: str
    ) -> bool:
        """Save or update push subscription."""
        try:
            async with self.database.session() as session:
                await session.execute(
                    text('''
                        INSERT INTO "Nappi"."push_subscriptions" 
                        (user_id, endpoint, p256dh_key, auth_key, created_at, updated_at)
                        VALUES (:user_id, :endpoint, :p256dh_key, :auth_key, NOW(), NOW())
                        ON CONFLICT (user_id) 
                        DO UPDATE SET 
                            endpoint = EXCLUDED.endpoint,
                            p256dh_key = EXCLUDED.p256dh_key,
                            auth_key = EXCLUDED.auth_key,
                            updated_at = NOW()
                    '''),
                    {
                        "user_id": user_id,
                        "endpoint": endpoint,
                        "p256dh_key": p256dh_key,
                        "auth_key": auth_key
                    }
                )
                await session.commit()
                logger.info(f"Saved push subscription for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save push subscription for user {user_id}: {e}")
            return False
    
    # Used by: alerts, send_notification (removes expired)
    async def remove_subscription(self, user_id: int) -> bool:
        """Remove push subscription."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        DELETE FROM "Nappi"."push_subscriptions"
                        WHERE user_id = :user_id
                    '''),
                    {"user_id": user_id}
                )
                await session.commit()
                deleted = result.rowcount > 0
                if deleted:
                    logger.info(f"Removed push subscription for user {user_id}")
                return deleted
        except Exception as e:
            logger.error(f"Failed to remove push subscription for user {user_id}: {e}")
            return False
    
    # Used by: send_notification
    async def get_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get subscription data for user."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT endpoint, p256dh_key, auth_key
                        FROM "Nappi"."push_subscriptions"
                        WHERE user_id = :user_id
                    '''),
                    {"user_id": user_id}
                )
                row = result.mappings().first()
                if row:
                    return {
                        "endpoint": row["endpoint"],
                        "keys": {
                            "p256dh": row["p256dh_key"],
                            "auth": row["auth_key"]
                        }
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get push subscription for user {user_id}: {e}")
            return None
    
    # Used by: alerts
    async def has_subscription(self, user_id: int) -> bool:
        """Whether user has active subscription."""
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    text('''
                        SELECT 1 FROM "Nappi"."push_subscriptions"
                        WHERE user_id = :user_id
                    '''),
                    {"user_id": user_id}
                )
                return result.first() is not None
        except Exception as e:
            logger.error(f"Failed to check subscription for user {user_id}: {e}")
            return False
    
    # Used by: alert_service
    async def send_notification(
        self,
        user_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        icon: str = "/logo.svg"
    ) -> bool:
        """Send push notification to user."""
        if not self.is_configured:
            logger.warning("Push notifications not configured, skipping")
            return False
        
        subscription = await self.get_subscription(user_id)
        if not subscription:
            logger.debug(f"No push subscription found for user {user_id}")
            return False
        
        try:
            from pywebpush import webpush, WebPushException
            
            payload = json.dumps({
                "title": title,
                "body": body,
                "icon": icon,
                "data": data or {}
            })
            
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=self._vapid_private_key,
                vapid_claims=self._vapid_claims
            )
            
            logger.info(f"Sent push notification to user {user_id}: {title}")
            return True
            
        except ImportError:
            logger.warning("pywebpush not installed, cannot send push notifications")
            return False
        except Exception as e:
            if hasattr(e, 'response') and e.response is not None:
                status = e.response.status_code
                if status in (404, 410):
                    # Subscription no longer valid, remove it
                    logger.info(f"Push subscription for user {user_id} is no longer valid, removing")
                    await self.remove_subscription(user_id)
            
            logger.error(f"Failed to send push notification to user {user_id}: {e}")
            return False


_push_service: Optional[PushService] = None


# Used by: alerts, alert_service
def get_push_service() -> PushService:
    """Push service singleton."""
    global _push_service
    if _push_service is None:
        _push_service = PushService()
    return _push_service
