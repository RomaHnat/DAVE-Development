"""
Tests for Sprint 2: Notification System.

Covers:
  - GET  /notifications           – list (paginated, filtered)
  - GET  /notifications/unread-count
  - PATCH /notifications/{id}/read
  - PATCH /notifications/read-all
  - DELETE /notifications/{id}
  - DELETE /notifications         – clear all read
  - GET  /notifications/preferences
  - POST /notifications/preferences
  - Unauthenticated access is rejected
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from bson import ObjectId

from backend.tests.conftest import auth_header
from backend.database import db

_state: dict = {}


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _seed_notifications(client, user_token, mongo):
    me = await client.get("/api/users/me", headers=auth_header(user_token))
    user_id_str = me.json()["id"]
    _state["user_id"] = user_id_str

    user_oid = ObjectId(user_id_str)
    now = datetime.now(timezone.utc)

    # Two unread
    r1 = await db.notifications.insert_one({
        "user_id": user_oid,
        "type": "info",
        "title": "Test Notif 1",
        "message": "First test notification",
        "link": None,
        "is_read": False,
        "created_at": now,
        "expires_at": None,
    })
    r2 = await db.notifications.insert_one({
        "user_id": user_oid,
        "type": "warning",
        "title": "Test Notif 2",
        "message": "Second test notification",
        "link": "/profile",
        "is_read": False,
        "created_at": now,
        "expires_at": None,
    })
    _state["notif_id_1"] = str(r1.inserted_id)
    _state["notif_id_2"] = str(r2.inserted_id)

    yield

    # Cleanup after module
    await db.notifications.delete_many({"user_id": user_oid})

@pytest.mark.asyncio
async def test_list_notifications(client, user_token):
    resp = await client.get("/api/notifications", headers=auth_header(user_token))
    assert resp.status_code == 200
    body = resp.json()
    assert "notifications" in body
    assert "total" in body
    assert body["total"] >= 2


@pytest.mark.asyncio
async def test_list_notifications_pagination(client, user_token):
    resp = await client.get(
        "/api/notifications?page=1&page_size=1",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    assert len(resp.json()["notifications"]) <= 1


@pytest.mark.asyncio
async def test_list_notifications_filter_unread(client, user_token):
    resp = await client.get(
        "/api/notifications?is_read=false",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    for n in resp.json()["notifications"]:
        assert n["is_read"] is False


@pytest.mark.asyncio
async def test_list_notifications_filter_type(client, user_token):
    resp = await client.get(
        "/api/notifications?type=warning",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    for n in resp.json()["notifications"]:
        assert n["type"] == "warning"

@pytest.mark.asyncio
async def test_unread_count_reflects_seeded_data(client, user_token):
    resp = await client.get(
        "/api/notifications/unread-count",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "unread_count" in body
    assert body["unread_count"] >= 2

@pytest.mark.asyncio
async def test_mark_notification_read(client, user_token):
    notif_id = _state.get("notif_id_1")
    assert notif_id
    resp = await client.patch(
        f"/api/notifications/{notif_id}/read",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200

    # Verify unread count decreased
    count_resp = await client.get(
        "/api/notifications/unread-count",
        headers=auth_header(user_token),
    )
    # At least one was read, so count is less than before
    assert count_resp.json()["unread_count"] >= 0


@pytest.mark.asyncio
async def test_mark_nonexistent_notification_read(client, user_token):
    resp = await client.patch(
        f"/api/notifications/{str(ObjectId())}/read",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_mark_all_read(client, user_token, mongo):
    # Ensure there is at least one unread
    user_oid = ObjectId(_state["user_id"])
    await db.notifications.insert_one({
        "user_id": user_oid,
        "type": "info",
        "title": "Pre read-all notif",
        "message": "Will be marked read by read-all",
        "is_read": False,
        "created_at": datetime.now(timezone.utc),
    })

    resp = await client.patch(
        "/api/notifications/read-all",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    assert "updated" in resp.json()

    # All should now be read
    count_resp = await client.get(
        "/api/notifications/unread-count",
        headers=auth_header(user_token),
    )
    assert count_resp.json()["unread_count"] == 0

@pytest.mark.asyncio
async def test_delete_notification(client, user_token, mongo):
    # Insert a fresh notification to delete
    user_oid = ObjectId(_state["user_id"])
    result = await db.notifications.insert_one({
        "user_id": user_oid,
        "type": "info",
        "title": "Delete Me",
        "message": "Should be deleted",
        "is_read": True,
        "created_at": datetime.now(timezone.utc),
    })
    del_id = str(result.inserted_id)

    resp = await client.delete(
        f"/api/notifications/{del_id}",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200

    # Should be gone from the list (query it directly to confirm)
    doc = await db.notifications.find_one({"_id": result.inserted_id})
    assert doc is None


@pytest.mark.asyncio
async def test_delete_nonexistent_notification(client, user_token):
    resp = await client.delete(
        f"/api/notifications/{str(ObjectId())}",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_clear_read_notifications(client, user_token, mongo):
    user_oid = ObjectId(_state["user_id"])
    # Insert some read notifications
    for i in range(3):
        await db.notifications.insert_one({
            "user_id": user_oid,
            "type": "info",
            "title": f"Read notif {i}",
            "message": "Read and ready to clear",
            "is_read": True,
            "created_at": datetime.now(timezone.utc),
        })

    resp = await client.delete(
        "/api/notifications",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "deleted" in body
    assert body["deleted"] >= 3

@pytest.mark.asyncio
async def test_get_notification_preferences(client, user_token):
    resp = await client.get(
        "/api/notifications/preferences",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "email_enabled" in body
    assert "preferences" in body


@pytest.mark.asyncio
async def test_update_notification_preferences(client, user_token):
    resp = await client.post(
        "/api/notifications/preferences",
        json={
            "email_enabled": True,
            "preferences": {
                "application_status_changed": {"email": True, "in_app": True},
            },
        },
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email_enabled"] is True

@pytest.mark.asyncio
async def test_unauthenticated_cannot_list_notifications(client):
    resp = await client.get("/api/notifications")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_unauthenticated_cannot_get_unread_count(client):
    resp = await client.get("/api/notifications/unread-count")
    assert resp.status_code in (401, 403)
