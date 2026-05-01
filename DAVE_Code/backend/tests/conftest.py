import asyncio
import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_NAME", "dave_test_db")
# Provide a dummy URL so config doesn't raise on import; mongomock replaces it
os.environ.setdefault("DATABASE_URL", "mongodb://localhost:27017")

from backend.main import app  # noqa: E402 – must come after env override
import backend.database as _db_module  # noqa: E402
from backend.database import db  # noqa: E402


async def _try_real_connection() -> bool:
    from motor.motor_asyncio import AsyncIOMotorClient
    from backend.config import DATABASE_URL, DATABASE_NAME
    try:
        client = AsyncIOMotorClient(DATABASE_URL, serverSelectionTimeoutMS=2000)
        await client[DATABASE_NAME].command("ping")
        _db_module.client = client
        _db_module._db = client[DATABASE_NAME]
        return True
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session")
async def mongo():
    from backend.config import DATABASE_NAME

    real_db_available = await _try_real_connection()

    if not real_db_available:
        import mongomock_motor
        mock_client = mongomock_motor.AsyncMongoMockClient()
        _db_module.client = mock_client
        _db_module._db = mock_client[DATABASE_NAME]

        # Seed the admin user required by admin_token fixture
        from backend.auth.security import hash_password
        await _db_module._db.users.insert_one({
            "email": "admin@dave.ie",
            "password_hash": hash_password("Admin@1234"),
            "full_name": "DAVE Administrator",
            "phone": None,
            "role": "admin",
            "is_active": True,
            "is_verified": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "failed_login_attempts": 0,
            "locked_until": None,
            "notification_preferences": {},
            "settings": {"language": "en", "timezone": "UTC", "date_format": "DD/MM/YYYY"},
        })
    else:
        # Seed admin into the test DB if not already present
        from backend.auth.security import hash_password
        existing = await _db_module._db.users.find_one({"role": {"$in": ["admin", "super_admin"]}})
        if not existing:
            await _db_module._db.users.insert_one({
                "email": "admin@dave.ie",
                "password_hash": hash_password("Admin@1234"),
                "full_name": "DAVE Administrator",
                "phone": None,
                "role": "admin",
                "is_active": True,
                "is_verified": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "failed_login_attempts": 0,
                "locked_until": None,
                "notification_preferences": {},
                "settings": {"language": "en", "timezone": "UTC", "date_format": "DD/MM/YYYY"},
            })

    yield db

    if real_db_available:
        from backend.database import close_mongo_connection
        await close_mongo_connection()
    else:
        _db_module._db = None
        _db_module.client = None

@pytest_asyncio.fixture(scope="module")
async def client(mongo):  # noqa: F811 – depends on DB being up
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

@pytest_asyncio.fixture(scope="module")
async def clean_users(mongo):
    yield
    await mongo.users.delete_many({"role": "applicant", "email": {"$regex": "^test_"}})

TEST_USER = {
    "email": "test_user@dave.ie",
    "password": "TestPass1",
    "full_name": "Test User",
}

TEST_ADMIN = {
    "email": "admin@dave.ie",
    "password": "Admin@1234",
}


@pytest_asyncio.fixture(scope="module")
async def user_token(client, clean_users):
    # Clean up beforehand in case a previous run left a stale record
    await db.users.delete_one({"email": TEST_USER["email"]})

    resp = await client.post("/api/auth/register", json=TEST_USER)
    assert resp.status_code == 200, f"Register failed: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture(scope="module")
async def admin_token(mongo):
    from datetime import timedelta
    from backend.auth.security import create_access_token

    admin = await mongo.users.find_one({"role": {"$in": ["admin", "super_admin"]}})
    assert admin is not None, "Admin user not seeded – run init_db or check conftest mongo fixture."
    token = create_access_token(
        data={"sub": str(admin["_id"])},
        expires_delta=timedelta(hours=1),
    )
    return token


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
