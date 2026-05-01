"""
Tests for Sprint 2: User Management & Profile System.

Covers:
  - GET /users/me  – fetch own profile
  - PUT /users/me  – update name/phone
  - GET /users/me/settings
  - PUT /users/me/settings
  - POST /users/me/change-password (error paths)
  - GET /users/me/activity
  - GET /users/me/sessions
  - GET /users/me/notification-preferences
  - POST /users/me/notification-preferences
  - Admin: GET /admin/users
  - Admin: GET /admin/users?role=...  (filter)
  - Admin: GET /admin/users/{user_id}
  - Admin: GET /admin/users/notanid  (invalid ObjectId)
  - Admin: PATCH /admin/users/{user_id}/status
  - Admin: GET /admin/activity-logs
  - Unauthenticated access is rejected
"""

import pytest
from backend.tests.conftest import TEST_USER, auth_header

@pytest.mark.asyncio
async def test_get_my_profile(client, user_token):
    resp = await client.get("/api/users/me", headers=auth_header(user_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == TEST_USER["email"]
    assert "password_hash" not in body
    assert "role" in body


@pytest.mark.asyncio
async def test_update_my_profile_name_and_phone(client, user_token):
    resp = await client.put(
        "/api/users/me",
        json={"full_name": "Updated Test Name", "phone": "+353871234567"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Updated Test Name"
    assert body["phone"] == "+353871234567"


@pytest.mark.asyncio
async def test_update_my_profile_empty_body_rejected(client, user_token):
    resp = await client.put(
        "/api/users/me",
        json={},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unauthenticated_cannot_get_profile(client):
    resp = await client.get("/api/users/me")
    assert resp.status_code in (401, 403)

@pytest.mark.asyncio
async def test_get_my_settings(client, user_token):
    resp = await client.get("/api/users/me/settings", headers=auth_header(user_token))
    assert resp.status_code == 200
    body = resp.json()
    assert "settings" in body


@pytest.mark.asyncio
async def test_update_my_settings(client, user_token):
    resp = await client.put(
        "/api/users/me/settings",
        json={
            "language": "en",
            "timezone": "Europe/Dublin",
            "date_format": "DD/MM/YYYY",
        },
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["settings"]["timezone"] == "Europe/Dublin"

@pytest.mark.asyncio
async def test_change_password_wrong_current(client, user_token):
    resp = await client.post(
        "/api/users/me/change-password",
        json={"current_password": "WrongPassword1", "new_password": "NewPass@99"},
        headers=auth_header(user_token),
    )
    assert resp.status_code in (400, 401)


@pytest.mark.asyncio
async def test_change_password_weak_new_password(client, user_token):
    resp = await client.post(
        "/api/users/me/change-password",
        json={"current_password": TEST_USER["password"], "new_password": "weak"},
        headers=auth_header(user_token),
    )
    assert resp.status_code in (400, 422)

@pytest.mark.asyncio
async def test_get_my_activity(client, user_token):
    resp = await client.get("/api/users/me/activity", headers=auth_header(user_token))
    assert resp.status_code == 200
    body = resp.json()
    assert "logs" in body
    assert "total" in body

@pytest.mark.asyncio
async def test_get_my_sessions(client, user_token):
    resp = await client.get("/api/users/me/sessions", headers=auth_header(user_token))
    assert resp.status_code == 200
    body = resp.json()
    assert "sessions" in body

@pytest.mark.asyncio
async def test_get_notification_preferences(client, user_token):
    resp = await client.get(
        "/api/users/me/notification-preferences",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "email_enabled" in body


@pytest.mark.asyncio
async def test_update_notification_preferences(client, user_token):
    resp = await client.post(
        "/api/users/me/notification-preferences",
        json={"email_enabled": False, "preferences": {}},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    assert resp.json()["email_enabled"] is False

@pytest.mark.asyncio
async def test_admin_list_users(client, admin_token):
    resp = await client.get("/api/admin/users", headers=auth_header(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert "users" in body
    assert "total" in body
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_admin_list_users_filter_by_role(client, admin_token):
    resp = await client.get(
        "/api/admin/users?role=admin",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    for user in resp.json()["users"]:
        assert user["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_list_users_search(client, admin_token):
    resp = await client.get(
        "/api/admin/users?search=admin",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["users"], list)


@pytest.mark.asyncio
async def test_admin_get_user_detail(client, admin_token):
    list_resp = await client.get("/api/admin/users", headers=auth_header(admin_token))
    users = list_resp.json()["users"]
    assert users, "No users in system"
    user_id = users[0]["id"]

    resp = await client.get(
        f"/api/admin/users/{user_id}",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == user_id
    assert "application_count" in body
    assert "recent_activity" in body


@pytest.mark.asyncio
async def test_admin_get_user_invalid_object_id(client, admin_token):
    resp = await client.get(
        "/api/admin/users/notanobjectid",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_get_nonexistent_user(client, admin_token):
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await client.get(
        f"/api/admin/users/{fake_id}",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_deactivate_and_reactivate_user(client, admin_token, user_token):
    # Get the test user's ID
    me_resp = await client.get("/api/users/me", headers=auth_header(user_token))
    user_id = me_resp.json()["id"]

    # Deactivate
    deact = await client.patch(
        f"/api/admin/users/{user_id}/status",
        json={"is_active": False},
        headers=auth_header(admin_token),
    )
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False

    # Reactivate so remaining tests can still use user_token
    react = await client.patch(
        f"/api/admin/users/{user_id}/status",
        json={"is_active": True},
        headers=auth_header(admin_token),
    )
    assert react.status_code == 200
    assert react.json()["is_active"] is True


@pytest.mark.asyncio
async def test_applicant_cannot_list_admin_users(client, user_token):
    resp = await client.get("/api/admin/users", headers=auth_header(user_token))
    assert resp.status_code in (401, 403)

@pytest.mark.asyncio
async def test_admin_activity_logs(client, admin_token):
    resp = await client.get(
        "/api/admin/activity-logs",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "logs" in body
    assert "total" in body


@pytest.mark.asyncio
async def test_admin_activity_logs_filter_by_action(client, admin_token):
    resp = await client.get(
        "/api/admin/activity-logs?action=login",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_applicant_cannot_access_activity_logs(client, user_token):
    resp = await client.get("/api/admin/activity-logs", headers=auth_header(user_token))
    assert resp.status_code in (401, 403)
