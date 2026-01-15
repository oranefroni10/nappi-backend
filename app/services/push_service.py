"""
Push Service - Handles Web Push notifications.

This service manages:
- Storing user push subscriptions
- Sending push notifications via pywebpush
- VAPID key management
"""

import json
import logging
from typing import Optional, Dict, Any

from app.core.database import get_database
from app.core.settings import settings
from sqlalchemy import text

logger = logging.getLogger(__name__)


class PushService:
    """
    Service for managing Web Push notifications.
    """
    
    def __init__(self):
        self.database = get_database()
        self._vapid_private_key: Optional[str] = None
        self._vapid_public_key: Optional[str] = None
        self._vapid_claims: Dict[str, str] = {}
        self._load_vapid_config()
    
    def _load_vapid_config(self):
        """Load VAPID configuration from environment."""
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
    
    @property
    def is_configured(self) -> bool:
        """Check if push notifications are properly configured."""
        return bool(self._vapid_private_key) and bool(self._vapid_public_key)
    
    @property
    def public_key(self) -> Optional[str]:
        """Get the VAPID public key for client subscription."""
        return self._vapid_public_key
    
    async def save_subscription(
        self,
        user_id: int,
        endpoint: str,
        p256dh_key: str,
        auth_key: str
    ) -> bool:
        """
        Save or update a user's push subscription.
        
        Args:
            user_id: The user ID
            endpoint: The push service endpoint URL
            p256dh_key: The P-256 public key
            auth_key: The authentication secret
            
        Returns:
            True if saved successfully
        """
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
    
    async def remove_subscription(self, user_id: int) -> bool:
        """
        Remove a user's push subscription.
        
        Args:
            user_id: The user ID
            
        Returns:
            True if removed successfully
        """
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
    
    async def get_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a user's push subscription.
        
        Args:
            user_id: The user ID
            
        Returns:
            Dictionary with subscription data or None
        """
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
    
    async def has_subscription(self, user_id: int) -> bool:
        """Check if a user has an active push subscription."""
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
    
    async def send_notification(
        self,
        user_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        icon: str = "/logo.svg"
    ) -> bool:
        """
        Send a push notification to a user.
        
        Args:
            user_id: The user ID
            title: Notification title
            body: Notification body text
            data: Optional additional data
            icon: Icon URL for the notification
            
        Returns:
            True if sent successfully
        """
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
            # Check if subscription is expired/invalid
            if hasattr(e, 'response') and e.response is not None:
                status = e.response.status_code
                if status in (404, 410):
                    # Subscription no longer valid, remove it
                    logger.info(f"Push subscription for user {user_id} is no longer valid, removing")
                    await self.remove_subscription(user_id)
            
            logger.error(f"Failed to send push notification to user {user_id}: {e}")
            return False


# Singleton instance
_push_service: Optional[PushService] = None


def get_push_service() -> PushService:
    """Get the push service singleton."""
    global _push_service
    if _push_service is None:
        _push_service = PushService()
    return _push_service
