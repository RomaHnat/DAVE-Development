from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId

from backend.database import db
import logging

logger = logging.getLogger(__name__)


DEFAULT_NOTIFICATION_PREFERENCES = {
    "application_status_changed": {"email": True, "in_app": True},
    "document_expiring": {"email": True, "in_app": True},
    "document_expired": {"email": True, "in_app": True},
    "application_approved": {"email": True, "in_app": True},
    "application_rejected": {"email": True, "in_app": True},
    "information_requested": {"email": True, "in_app": True},
    "new_message": {"email": True, "in_app": True},
    "system_update": {"email": True, "in_app": True},
}


def build_default_user_notification_settings() -> dict:
    return {
        "email_enabled": True,
        "preferences": DEFAULT_NOTIFICATION_PREFERENCES,
    }


async def _maybe_send_email_notification(
    user_id: ObjectId, type: str, title: str, message: str
) -> None:
    try:
        user = await db.users.find_one(
            {"_id": user_id},
            {"email": 1, "full_name": 1, "notification_preferences": 1},
        )
        if not user:
            return
        prefs = user.get("notification_preferences") or {}
        if not prefs.get("email_enabled", True):
            return
        type_pref = prefs.get("preferences", {}).get(type, {"email": True})
        if not type_pref.get("email", True):
            return
        from backend.services.email_service import send_email
        await send_email(
            to=user["email"],
            subject=f"DAVE \u2013 {title}",
            body=(
                f"Hello {user.get('full_name', '')}!\n\n"
                f"{message}\n\n"
                "Best regards,\nThe DAVE Team"
            ),
        )
    except Exception as exc:
        logger.warning("Failed to send notification email: %s", exc)


async def create_notification(
    user_id: ObjectId,
    type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    expires_in_days: Optional[int] = None,
    send_email_if_enabled: bool = True,
) -> str:
    now = datetime.now(timezone.utc)
    expires_at = None
    if expires_in_days is not None:
        expires_at = now + timedelta(days=expires_in_days)

    result = await db.notifications.insert_one(
        {
            "user_id": user_id,
            "type": type,
            "title": title,
            "message": message,
            "link": link,
            "is_read": False,
            "created_at": now,
            "expires_at": expires_at,
        }
    )
    if send_email_if_enabled:
        await _maybe_send_email_notification(user_id, type, title, message)
    return str(result.inserted_id)


async def get_user_notifications(
    user_id: ObjectId,
    page: int = 1,
    page_size: int = 20,
    is_read: Optional[bool] = None,
    type: Optional[str] = None,
) -> tuple[list, int]:
    query = {"user_id": user_id}
    if is_read is not None:
        query["is_read"] = is_read
    if type:
        query["type"] = type

    total = await db.notifications.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.notifications.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    notifications = await cursor.to_list(length=page_size)
    return notifications, total


async def unread_count(user_id: ObjectId) -> int:
    return await db.notifications.count_documents({"user_id": user_id, "is_read": False})


async def mark_as_read(user_id: ObjectId, notification_id: str) -> bool:
    if not ObjectId.is_valid(notification_id):
        return False
    result = await db.notifications.update_one(
        {
            "_id": ObjectId(notification_id),
            "user_id": user_id,
        },
        {
            "$set": {
                "is_read": True,
                "read_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count > 0


async def mark_all_as_read(user_id: ObjectId) -> int:
    result = await db.notifications.update_many(
        {
            "user_id": user_id,
            "is_read": False,
        },
        {
            "$set": {
                "is_read": True,
                "read_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count


async def delete_notification(user_id: ObjectId, notification_id: str) -> bool:
    if not ObjectId.is_valid(notification_id):
        return False
    result = await db.notifications.delete_one(
        {
            "_id": ObjectId(notification_id),
            "user_id": user_id,
        }
    )
    return result.deleted_count > 0


async def clear_read_notifications(user_id: ObjectId) -> int:
    result = await db.notifications.delete_many(
        {
            "user_id": user_id,
            "is_read": True,
        }
    )
    return result.deleted_count


async def delete_old_notifications(days: int = 30) -> int:
    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.notifications.delete_many(
        {
            "$or": [
                {"created_at": {"$lt": threshold}, "is_read": True},
                {"expires_at": {"$lt": datetime.now(timezone.utc)}},
            ]
        }
    )
    return result.deleted_count
