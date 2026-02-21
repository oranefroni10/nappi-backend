"""
Alerts API - Server-Sent Events and alert management endpoints.

Provides:
- GET /alerts/stream - SSE endpoint for real-time alerts
- GET /alerts/history - Fetch alert history with pagination
- POST /alerts/{id}/read - Mark a single alert as read
- POST /alerts/read-all - Mark all alerts as read
- GET /alerts/unread-count - Get count of unread alerts
- DELETE /alerts - Delete alerts by IDs
- POST /push/subscribe - Subscribe to push notifications
- POST /push/unsubscribe - Unsubscribe from push notifications
- GET /push/vapid-key - Get VAPID public key for subscription
"""

import asyncio
import json
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.alert_service import get_alert_service, get_sse_manager, Alert
from app.services.push_service import get_push_service
from app.core.constants import SSE_KEEPALIVE_SECONDS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ============================================
# Request/Response Models
# ============================================

class AlertResponse(BaseModel):
    """Single alert response."""
    id: int
    baby_id: int
    user_id: int
    type: str
    title: str
    message: str
    severity: str
    metadata: Optional[dict] = None
    read: bool
    created_at: str


class AlertListResponse(BaseModel):
    """List of alerts response."""
    alerts: List[AlertResponse]
    total_count: int


class UnreadCountResponse(BaseModel):
    """Unread count response."""
    count: int


class MarkReadResponse(BaseModel):
    """Mark as read response."""
    success: bool


class MarkAllReadResponse(BaseModel):
    """Mark all as read response."""
    updated_count: int


class DeleteAlertsRequest(BaseModel):
    """Delete alerts request."""
    alert_ids: List[int]


class DeleteAlertsResponse(BaseModel):
    """Delete alerts response."""
    deleted_count: int


class PushSubscriptionRequest(BaseModel):
    """Push subscription request."""
    endpoint: str
    keys: dict  # Contains p256dh and auth


class PushSubscriptionResponse(BaseModel):
    """Push subscription response."""
    success: bool
    message: str


class VapidKeyResponse(BaseModel):
    """VAPID key response."""
    public_key: Optional[str]
    configured: bool


# ============================================
# SSE Endpoint
# ============================================

# Used by: Notifications page — real-time SSE alert stream (via useAlerts hook)
@router.get("/stream")
async def alerts_stream(user_id: int = Query(..., description="User ID to subscribe for")):
    """
    Server-Sent Events stream for real-time alerts.
    
    Connect to this endpoint to receive real-time alerts.
    Each event is a JSON-encoded Alert object.
    
    Example usage in JavaScript:
    ```
    const eventSource = new EventSource('/alerts/stream?user_id=123');
    eventSource.onmessage = (event) => {
        const alert = JSON.parse(event.data);
        console.log('New alert:', alert);
    };
    ```
    """
    sse_manager = get_sse_manager()
    queue = await sse_manager.subscribe(user_id)
    
    async def event_generator():
        try:
            # Send initial connection event
            yield f"event: connected\ndata: {{}}\n\n"
            
            while True:
                try:
                    # Wait for new alerts with timeout for keepalive
                    alert = await asyncio.wait_for(queue.get(), timeout=float(SSE_KEEPALIVE_SECONDS))
                    yield f"data: {json.dumps(alert.to_dict())}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await sse_manager.unsubscribe(user_id, queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


# ============================================
# Alert History Endpoints
# ============================================

# Used by: Notifications page — paginated alert history list
@router.get("/history", response_model=AlertListResponse)
async def get_alerts_history(
    user_id: int = Query(..., description="User ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum alerts to return"),
    offset: int = Query(0, ge=0, description="Number of alerts to skip"),
    unread_only: bool = Query(False, description="Only return unread alerts")
):
    """
    Get alert history for a user with pagination.
    """
    alert_service = get_alert_service()
    alerts = await alert_service.get_alerts_for_user(
        user_id=user_id,
        limit=limit,
        offset=offset,
        unread_only=unread_only
    )
    
    # Get total count for pagination
    total_count = len(alerts)  # Simplified; could add separate count query
    
    return AlertListResponse(
        alerts=[
            AlertResponse(
                id=a.id,
                baby_id=a.baby_id,
                user_id=a.user_id,
                type=a.type,
                title=a.title,
                message=a.message,
                severity=a.severity,
                metadata=a.metadata,
                read=a.read,
                created_at=a.created_at.isoformat() if a.created_at else ""
            )
            for a in alerts
        ],
        total_count=total_count
    )


# Used by: Notifications page — unread badge count
@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user_id: int = Query(..., description="User ID")
):
    """
    Get the count of unread alerts for a user.
    """
    alert_service = get_alert_service()
    count = await alert_service.get_unread_count(user_id)
    return UnreadCountResponse(count=count)


# Used by: Notifications page — mark individual alert as read
@router.post("/{alert_id}/read", response_model=MarkReadResponse)
async def mark_alert_read(
    alert_id: int,
    user_id: int = Query(..., description="User ID")
):
    """
    Mark a single alert as read.
    """
    alert_service = get_alert_service()
    success = await alert_service.mark_as_read(alert_id, user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found or doesn't belong to user"
        )
    
    return MarkReadResponse(success=True)


# Used by: Notifications page — "mark all as read" button
@router.post("/read-all", response_model=MarkAllReadResponse)
async def mark_all_alerts_read(
    user_id: int = Query(..., description="User ID")
):
    """
    Mark all alerts as read for a user.
    """
    alert_service = get_alert_service()
    updated_count = await alert_service.mark_all_as_read(user_id)
    return MarkAllReadResponse(updated_count=updated_count)


# Used by: Notifications page — delete individual or bulk alerts
@router.delete("", response_model=DeleteAlertsResponse)
async def delete_alerts(
    request: DeleteAlertsRequest,
    user_id: int = Query(..., description="User ID")
):
    """
    Delete alerts by IDs for a user.
    """
    if not request.alert_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="alert_ids must not be empty"
        )
    if len(request.alert_ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete more than 100 alerts at once"
        )

    alert_service = get_alert_service()
    deleted_count = await alert_service.delete_alerts(request.alert_ids, user_id)
    return DeleteAlertsResponse(deleted_count=deleted_count)


# ============================================
# Push Notification Endpoints
# ============================================

push_router = APIRouter(prefix="/push", tags=["push-notifications"])


# Used by: User Profile page — fetches VAPID key for push notification subscription
@push_router.get("/vapid-key", response_model=VapidKeyResponse)
async def get_vapid_public_key():
    """
    Get the VAPID public key for subscribing to push notifications.
    
    The client needs this key to create a push subscription.
    """
    push_service = get_push_service()
    return VapidKeyResponse(
        public_key=push_service.public_key,
        configured=push_service.is_configured
    )


# Used by: User Profile page — enable push notifications toggle
@push_router.post("/subscribe", response_model=PushSubscriptionResponse)
async def subscribe_to_push(
    request: PushSubscriptionRequest,
    user_id: int = Query(..., description="User ID")
):
    """
    Subscribe to push notifications.
    
    Send the subscription object obtained from browser's PushManager.subscribe().
    """
    push_service = get_push_service()
    
    if not push_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications are not configured on this server"
        )
    
    # Extract keys from the subscription
    p256dh_key = request.keys.get("p256dh")
    auth_key = request.keys.get("auth")
    
    if not p256dh_key or not auth_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid subscription: missing p256dh or auth keys"
        )
    
    success = await push_service.save_subscription(
        user_id=user_id,
        endpoint=request.endpoint,
        p256dh_key=p256dh_key,
        auth_key=auth_key
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save push subscription"
        )
    
    return PushSubscriptionResponse(
        success=True,
        message="Successfully subscribed to push notifications"
    )


# Used by: User Profile page — disable push notifications toggle
@push_router.post("/unsubscribe", response_model=PushSubscriptionResponse)
async def unsubscribe_from_push(
    user_id: int = Query(..., description="User ID")
):
    """
    Unsubscribe from push notifications.
    """
    push_service = get_push_service()
    success = await push_service.remove_subscription(user_id)
    
    return PushSubscriptionResponse(
        success=True,
        message="Successfully unsubscribed from push notifications" if success else "No subscription found"
    )


# Used by: User Profile page — checks if push notifications are active for toggle state
@push_router.get("/status")
async def get_push_status(
    user_id: int = Query(..., description="User ID")
):
    """
    Check if a user has an active push subscription.
    """
    push_service = get_push_service()
    has_subscription = await push_service.has_subscription(user_id)
    
    return {
        "subscribed": has_subscription,
        "push_configured": push_service.is_configured
    }
