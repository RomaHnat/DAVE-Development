from backend.database import connect_to_mongo, close_mongo_connection
from motor.motor_asyncio import AsyncIOMotorClient
from backend.config import DATABASE_URL, DATABASE_NAME
import asyncio

async def init():
    await connect_to_mongo()
    
    # Access db from the connected client
    from backend.database import db
    
    print("Creating database indexes...")

    # Create indexes for better query performance
    await db.users.create_index("email", unique=True)
    await db.applications.create_index("case_id", unique=True)
    await db.documents.create_index("application_id")
    
    # Audit logs indexes for activity tracking
    await db.audit_logs.create_index("timestamp")
    await db.audit_logs.create_index("user_id")
    await db.audit_logs.create_index("action")
    await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)])

    print("All database indexes created successfully")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(init())
