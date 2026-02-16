from motor.motor_asyncio import AsyncIOMotorClient
from backend.config import DATABASE_URL, DATABASE_NAME

client: AsyncIOMotorClient | None = None
db = None

async def connect_to_mongo():
    global client, db
    client = AsyncIOMotorClient(
        DATABASE_URL,
        maxPoolSize=10,
        minPoolSize=1,
    )
    db = client[DATABASE_NAME]

async def close_mongo_connection():
    client.close()

async def health_check():
    await db.command("ping")
    return True