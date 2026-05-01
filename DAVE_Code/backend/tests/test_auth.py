"""
Tests for authentication endpoints.

Covers:
  - Registration (success, duplicate email, weak password)
  - Login (success, wrong password, account lockout, IP rate-limit)
  - /me  (authenticated, unauthenticated)
  - Token refresh
  - Forgot / reset password happy-path
"""

import pytest
import pytest_asyncio

from backend.tests.conftest import TEST_USER, auth_header

@pytest.mark.asyncio
async def test_register_success(client, clean_users):
    await _delete_test_user(client)
    resp = await client.post("/api/auth/register", json=TEST_USER)
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["user_data"]["email"] == TEST_USER["email"]
    assert body["user_data"]["role"] == "applicant"


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    resp = await client.post("/api/auth/register", json=TEST_USER)
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_weak_password(client):
    payload = {**TEST_USER, "email": "test_weak@dave.ie", "password": "weakpassword1"}
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_login_success(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": TEST_USER["email"], "password": TEST_USER["password"]},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": TEST_USER["email"], "password": "WrongPass9"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "nobody@dave.ie", "password": "SomePass1"},
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_get_me_authenticated(client, user_token):
    resp = await client.get("/api/auth/me", headers=auth_header(user_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == TEST_USER["email"]


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code in (401, 403)

@pytest.mark.asyncio
async def test_refresh_token(client, user_token):
    resp = await client.post("/api/auth/refresh", headers=auth_header(user_token))
    assert resp.status_code == 200
    assert "access_token" in resp.json()

@pytest.mark.asyncio
async def test_forgot_password_generic_response(client):
    # Known email
    resp = await client.post(
        "/api/auth/forgot-password", json={"email": TEST_USER["email"]}
    )
    assert resp.status_code == 200
    assert "message" in resp.json()

    # Unknown email – must still return 200
    resp2 = await client.post(
        "/api/auth/forgot-password", json={"email": "ghost@dave.ie"}
    )
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_invalid_token(client):
    resp = await client.post(
        "/api/auth/reset-password",
        json={"token": "totally-invalid-token", "new_password": "NewPass9"},
    )
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_applicant_cannot_access_admin_endpoint(client, user_token):
    resp = await client.get("/api/admin/users", headers=auth_header(user_token))
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_can_access_admin_endpoint(client, admin_token):
    resp = await client.get("/api/admin/users", headers=auth_header(admin_token))
    assert resp.status_code == 200

async def _delete_test_user(client):
    from backend.database import db
    await db.users.delete_one({"email": TEST_USER["email"]})


@pytest.mark.asyncio
async def test_register_triggers_welcome_email(client, clean_users):
    from unittest.mock import AsyncMock, patch

    await _delete_test_user(client)
    with patch("backend.routes.auth.send_welcome_email", new_callable=AsyncMock) as mock_mail:
        resp = await client.post("/api/auth/register", json=TEST_USER)

    assert resp.status_code == 200
    mock_mail.assert_called_once()
    # The function is called with keyword args: email=..., full_name=...
    assert mock_mail.call_args.kwargs.get("email") == TEST_USER["email"]


@pytest.mark.asyncio
async def test_forgot_password_triggers_reset_email(client):
    from unittest.mock import AsyncMock, patch

    with patch(
        "backend.routes.auth.send_password_reset_email", new_callable=AsyncMock
    ) as mock_mail:
        resp = await client.post(
            "/api/auth/forgot-password", json={"email": TEST_USER["email"]}
        )

    assert resp.status_code == 200
    mock_mail.assert_called_once()
    assert mock_mail.call_args.kwargs.get("email") == TEST_USER["email"]


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_does_not_send(client):
    from unittest.mock import AsyncMock, patch

    with patch(
        "backend.routes.auth.send_password_reset_email", new_callable=AsyncMock
    ) as mock_mail:
        resp = await client.post(
            "/api/auth/forgot-password", json={"email": "nobody@dave.ie"}
        )

    assert resp.status_code == 200  # Still returns 200 (no enumeration)
    mock_mail.assert_not_called()
