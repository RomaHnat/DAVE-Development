from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from typing import Optional
import asyncio
import json
from datetime import datetime, timezone

from bson import ObjectId

from backend.auth.dependencies import get_current_active_user
from backend.database import db
from backend.schemas.notification import (
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationResponse,
    UnreadCountResponse,
)
from backend.services.notification_service import (
    build_default_user_notification_settings,
    clear_read_notifications,
    delete_notification,
    get_user_notifications,
    mark_all_as_read,
    mark_as_read,
    unread_count,
)


router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_read: Optional[bool] = Query(None),
    type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_active_user),
):
    notifications, total = await get_user_notifications(
        user_id=current_user["_id"],
        page=page,
        page_size=page_size,
        is_read=is_read,
        type=type,
    )
    response_items = [
        NotificationResponse(
            id=str(item["_id"]),
            type=item["type"],
            title=item["title"],
            message=item["message"],
            link=item.get("link"),
            is_read=item.get("is_read", False),
            created_at=item["created_at"],
            expires_at=item.get("expires_at"),
        )
        for item in notifications
    ]
    return NotificationListResponse(
        notifications=response_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(current_user: dict = Depends(get_current_active_user)):
    count = await unread_count(current_user["_id"])
    return UnreadCountResponse(unread_count=count)


@router.patch("/{notification_id}/read", response_model=dict)
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    success = await mark_as_read(current_user["_id"], notification_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {"message": "Notification marked as read"}


@router.patch("/read-all", response_model=dict)
async def mark_notifications_read_all(current_user: dict = Depends(get_current_active_user)):
    updated = await mark_all_as_read(current_user["_id"])
    return {"message": "Notifications marked as read", "updated": updated}


@router.delete("/{notification_id}", response_model=dict)
async def delete_single_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    success = await delete_notification(current_user["_id"], notification_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {"message": "Notification deleted"}


@router.delete("", response_model=dict)
async def clear_all_read_notifications(current_user: dict = Depends(get_current_active_user)):
    deleted = await clear_read_notifications(current_user["_id"])
    return {"message": "Read notifications cleared", "deleted": deleted}


@router.get("/stream")
async def notification_stream(current_user: dict = Depends(get_current_active_user)):

    user_id = current_user["_id"]

    async def _generate():
        try:
            while True:
                count = await unread_count(user_id)
                data = json.dumps({
                    "unread_count": count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                yield f"data: {data}\n\n"
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(current_user: dict = Depends(get_current_active_user)):
    preferences = current_user.get("notification_preferences")
    if not preferences:
        preferences = build_default_user_notification_settings()
        await db.users.update_one(
            {"_id": current_user["_id"]},
            {"$set": {"notification_preferences": preferences}},
        )
    return NotificationPreferencesResponse(
        email_enabled=preferences.get("email_enabled", True),
        preferences=preferences.get("preferences", {}),
    )


@router.post("/preferences", response_model=NotificationPreferencesResponse)
async def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    current_user: dict = Depends(get_current_active_user),
):
    existing = current_user.get("notification_preferences") or build_default_user_notification_settings()

    updated = {
        "email_enabled": payload.email_enabled if payload.email_enabled is not None else existing.get("email_enabled", True),
        "preferences": payload.preferences if payload.preferences is not None else existing.get("preferences", {}),
    }

    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"notification_preferences": updated}},
    )

    return NotificationPreferencesResponse(
        email_enabled=updated["email_enabled"],
        preferences=updated["preferences"],
    )
