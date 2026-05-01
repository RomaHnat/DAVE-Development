from backend.database import connect_to_mongo, close_mongo_connection
from backend.config import DATABASE_URL, DATABASE_NAME
import asyncio


async def init():
    await connect_to_mongo()

    from backend.database import db

    print("Creating database indexes...")

    await db.users.create_index("email", unique=True)

    await db.documents.create_index("application_id")
    await db.documents.create_index("status")
    await db.documents.create_index("expiry_date")
    await db.documents.create_index([("application_id", 1), ("uploaded_at", -1)])

    await db.audit_logs.create_index("timestamp")
    await db.audit_logs.create_index("user_id")
    await db.audit_logs.create_index("action")
    await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)])

    await db.notifications.create_index("user_id")
    await db.notifications.create_index([("user_id", 1), ("is_read", 1), ("created_at", -1)])
    await db.notifications.create_index("expires_at")

    await db.user_sessions.create_index("session_id", unique=True)
    await db.user_sessions.create_index([("user_id", 1), ("is_active", 1), ("last_active", -1)])
    await db.user_sessions.create_index("expires_at")

    await db.one_time_tokens.create_index("token", unique=True)
    await db.one_time_tokens.create_index([("token_type", 1), ("is_used", 1), ("expires_at", 1)])

    await db.application_types.create_index("type_name")
    await db.application_types.create_index("status")

    await db.applications.create_index("case_id", unique=True)
    await db.applications.create_index("user_id")
    await db.applications.create_index("status")
    await db.applications.create_index("submitted_at")
    await db.applications.create_index("application_type_id")
    await db.applications.create_index([("user_id", 1), ("status", 1), ("created_at", -1)])

    await db.application_events.create_index("application_id")
    await db.application_events.create_index([("application_id", 1), ("timestamp", 1)])

    await db.counters.create_index("_id")

    print("All database indexes created successfully.")

    print("Running seeds...")
    from backend.seeds.application_types import seed_all
    await seed_all()

    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(init())
