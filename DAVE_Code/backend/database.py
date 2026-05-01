from motor.motor_asyncio import AsyncIOMotorClient
from backend.config import DATABASE_URL, DATABASE_NAME

client: AsyncIOMotorClient | None = None
_db = None


class DatabaseProxy:
    def __getattr__(self, item):
        if _db is None:
            raise RuntimeError("Database connection is not initialized")
        return getattr(_db, item)


db = DatabaseProxy()

async def connect_to_mongo():
    global client, _db
    client = AsyncIOMotorClient(
        DATABASE_URL,
        maxPoolSize=10,
        minPoolSize=1,
    )
    _db = client[DATABASE_NAME]

async def close_mongo_connection():
    client.close()

async def get_motor_db():

    if _db is None:
        raise RuntimeError("Database connection is not initialized")
    return _db