from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from bson import ObjectId

from backend.database import db


SESSION_TTL_HOURS = 12


async def create_session(user_id: ObjectId, ip_address: Optional[str], user_agent: Optional[str]) -> str:
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.user_sessions.insert_one(
        {
            "session_id": session_id,
            "user_id": user_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "location": None,
            "is_active": True,
            "created_at": now,
            "last_active": now,
            "expires_at": now + timedelta(hours=SESSION_TTL_HOURS),
        }
    )
    return session_id


async def touch_session(session_id: str) -> None:
    await db.user_sessions.update_one(
        {"session_id": session_id, "is_active": True},
        {"$set": {"last_active": datetime.now(timezone.utc)}},
    )


async def get_session(session_id: str) -> Optional[dict]:
    now = datetime.now(timezone.utc)
    return await db.user_sessions.find_one(
        {
            "session_id": session_id,
            "is_active": True,
            "expires_at": {"$gt": now},
        }
    )


async def get_user_sessions(user_id: ObjectId) -> list[dict]:
    cursor = db.user_sessions.find(
        {
            "user_id": user_id,
            "is_active": True,
        }
    ).sort("last_active", -1)
    return await cursor.to_list(length=200)


async def revoke_session(user_id: ObjectId, session_id: str) -> bool:
    result = await db.user_sessions.update_one(
        {
            "user_id": user_id,
            "session_id": session_id,
            "is_active": True,
        },
        {
            "$set": {
                "is_active": False,
                "revoked_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count > 0


async def revoke_all_other_sessions(user_id: ObjectId, current_session_id: str) -> int:
    result = await db.user_sessions.update_many(
        {
            "user_id": user_id,
            "session_id": {"$ne": current_session_id},
            "is_active": True,
        },
        {
            "$set": {
                "is_active": False,
                "revoked_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count
