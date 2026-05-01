from datetime import datetime, timedelta, timezone
import secrets
from typing import Optional

from backend.database import db


async def generate_one_time_token(
    user_id: str,
    token_type: str,
    expires_hours: int = 24,
    metadata: Optional[dict] = None,
) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.one_time_tokens.insert_one(
        {
            "token": token,
            "user_id": user_id,
            "token_type": token_type,
            "metadata": metadata or {},
            "is_used": False,
            "created_at": now,
            "expires_at": now + timedelta(hours=expires_hours),
        }
    )
    return token


async def verify_one_time_token(token: str, token_type: str) -> Optional[dict]:
    now = datetime.now(timezone.utc)
    token_doc = await db.one_time_tokens.find_one(
        {
            "token": token,
            "token_type": token_type,
            "is_used": False,
            "expires_at": {"$gt": now},
        }
    )
    return token_doc


async def invalidate_token(token: str) -> None:
    await db.one_time_tokens.update_one(
        {"token": token},
        {"$set": {"is_used": True, "used_at": datetime.now(timezone.utc)}},
    )
