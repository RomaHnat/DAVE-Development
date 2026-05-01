from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId

from backend.auth.dependencies import get_current_active_user, get_current_token_payload
from backend.auth.security import verify_password, hash_password
from backend.schemas.user import (
    UserUpdateRequest, 
    UserDetailResponse,
    ActivityLogResponse,
    ActivityLogListResponse
)
from backend.schemas.settings import (
    EmailChangeConfirmRequest,
    EmailChangeRequest,
    PasswordChangeRequest,
    SessionInfo,
    SessionListResponse,
    UserSettings,
    UserSettingsResponse,
)
from backend.schemas.notification import (
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
)
from backend.database import db
from backend.services.audit_service import log_user_action, get_user_activity
from backend.services.notification_service import (
    build_default_user_notification_settings,
    create_notification,
)
from backend.services.session_service import (
    get_user_sessions,
    revoke_all_other_sessions,
    revoke_session,
)
from backend.services.token_service import (
    generate_one_time_token,
    invalidate_token,
    verify_one_time_token,
)

router = APIRouter(prefix="/users", tags=["Users"])


def _to_user_response(user_doc: dict) -> UserDetailResponse:
    return UserDetailResponse(
        id=str(user_doc["_id"]),
        email=user_doc["email"],
        full_name=user_doc["full_name"],
        phone=user_doc.get("phone"),
        role=user_doc["role"],
        is_active=user_doc["is_active"],
        is_verified=user_doc.get("is_verified", False),
        created_at=user_doc["created_at"],
        updated_at=user_doc.get("updated_at"),
        last_login=user_doc.get("last_login"),
    )

@router.get("/me", response_model=UserDetailResponse)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_active_user)
):
    return _to_user_response(current_user)

@router.put("/me", response_model=UserDetailResponse)
async def update_user_profile(
    updates: UserUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    update_data = {}
    
    # Only include fields that were provided
    if updates.full_name is not None:
        update_data["full_name"] = updates.full_name
    if updates.phone is not None:
        update_data["phone"] = updates.phone
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )
    
    # Always update the timestamp
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    # Update user in database
    result = await db.users.update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        # Check if user still exists
        user_exists = await db.users.find_one({"_id": ObjectId(current_user["_id"])})
        if not user_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
    
    # Log the action
    await log_user_action(
        user_id=str(current_user["_id"]),
        action="profile_updated",
        entity_type="user",
        entity_id=str(current_user["_id"]),
        details={"updated_fields": list(update_data.keys())},
        request=request
    )
    
    # Fetch and return updated user
    updated_user = await db.users.find_one({"_id": ObjectId(current_user["_id"])})
    
    return _to_user_response(updated_user)


@router.patch("/me/email", response_model=dict)
async def request_email_change(
    payload: EmailChangeRequest,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
):
    new_email = payload.new_email.strip().lower()
    if new_email == current_user["email"].lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New email must be different from current email",
        )

    existing = await db.users.find_one({"email": new_email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use",
        )

    token = await generate_one_time_token(
        user_id=str(current_user["_id"]),
        token_type="email_change",
        expires_hours=24,
        metadata={"new_email": new_email},
    )

    await create_notification(
        user_id=current_user["_id"],
        type="info",
        title="Email change requested",
        message="Use the verification token to confirm your new email.",
    )

    await log_user_action(
        user_id=str(current_user["_id"]),
        action="email_change_requested",
        entity_type="user",
        entity_id=str(current_user["_id"]),
        details={"new_email": new_email},
        request=request,
    )

    return {
        "message": "Email change token generated. Confirm with /api/users/me/email/confirm",
        "token": token,
    }


@router.post("/me/email/confirm", response_model=UserDetailResponse)
async def confirm_email_change(
    payload: EmailChangeConfirmRequest,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
):
    token_doc = await verify_one_time_token(payload.token, "email_change")
    if not token_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    if str(token_doc["user_id"]) != str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token does not belong to current user",
        )

    new_email = token_doc.get("metadata", {}).get("new_email")
    if not new_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token metadata is invalid",
        )

    existing = await db.users.find_one({"email": new_email, "_id": {"$ne": current_user["_id"]}})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use",
        )

    await db.users.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "email": new_email,
                "is_verified": False,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    await invalidate_token(payload.token)

    await log_user_action(
        user_id=str(current_user["_id"]),
        action="email_changed",
        entity_type="user",
        entity_id=str(current_user["_id"]),
        details={"new_email": new_email},
        request=request,
    )

    updated_user = await db.users.find_one({"_id": current_user["_id"]})
    return _to_user_response(updated_user)

@router.get("/me/activity", response_model=ActivityLogListResponse)
async def get_my_activity(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    current_user: dict = Depends(get_current_active_user)
):
    logs, total = await get_user_activity(
        user_id=str(current_user["_id"]),
        page=page,
        page_size=page_size,
        action=action
    )
    
    # Convert logs to response format (exclude IP and user agent for regular users)
    activity_responses = [
        ActivityLogResponse(
            id=str(log["_id"]),
            action=log["action"],
            entity_type=log.get("entity_type"),
            entity_id=str(log["entity_id"]) if log.get("entity_id") else None,
            details=log.get("details"),
            timestamp=log["timestamp"]
        )
        for log in logs
    ]
    
    return ActivityLogListResponse(
        logs=activity_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/me/notification-preferences", response_model=NotificationPreferencesResponse)
async def get_my_notification_preferences(current_user: dict = Depends(get_current_active_user)):
    preferences = current_user.get("notification_preferences")
    if not preferences:
        preferences = build_default_user_notification_settings()
        await db.users.update_one(
            {"_id": current_user["_id"]},
            {"$set": {"notification_preferences": preferences}},
        )

    return NotificationPreferencesResponse(
        email_enabled=preferences.get("email_enabled", True),
        preferences=preferences.get("preferences", {}),
    )


@router.post("/me/notification-preferences", response_model=NotificationPreferencesResponse)
async def update_my_notification_preferences(
    payload: NotificationPreferencesUpdate,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
):
    current_prefs = current_user.get("notification_preferences") or build_default_user_notification_settings()
    updated = {
        "email_enabled": payload.email_enabled if payload.email_enabled is not None else current_prefs.get("email_enabled", True),
        "preferences": payload.preferences if payload.preferences is not None else current_prefs.get("preferences", {}),
    }
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"notification_preferences": updated, "updated_at": datetime.now(timezone.utc)}},
    )
    await log_user_action(
        user_id=str(current_user["_id"]),
        action="notification_preferences_updated",
        entity_type="user",
        entity_id=str(current_user["_id"]),
        details={},
        request=request,
    )
    return NotificationPreferencesResponse(
        email_enabled=updated["email_enabled"],
        preferences=updated["preferences"],
    )


@router.get("/me/settings", response_model=UserSettingsResponse)
async def get_my_settings(current_user: dict = Depends(get_current_active_user)):
    settings_data = current_user.get("settings") or {
        "language": "en",
        "timezone": "UTC",
        "date_format": "DD/MM/YYYY",
    }
    return UserSettingsResponse(settings=UserSettings(**settings_data))


@router.put("/me/settings", response_model=UserSettingsResponse)
async def update_my_settings(
    payload: UserSettings,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
):
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "settings": payload.model_dump(),
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    await log_user_action(
        user_id=str(current_user["_id"]),
        action="settings_updated",
        entity_type="user",
        entity_id=str(current_user["_id"]),
        details=payload.model_dump(),
        request=request,
    )
    return UserSettingsResponse(settings=payload)


@router.post("/me/change-password", response_model=dict)
async def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
):
    if not verify_password(payload.current_password, current_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    new_hash = hash_password(payload.new_password)
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "password_hash": new_hash,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    await db.user_sessions.update_many(
        {"user_id": current_user["_id"], "is_active": True},
        {
            "$set": {
                "is_active": False,
                "revoked_at": datetime.now(timezone.utc),
            }
        },
    )

    await create_notification(
        user_id=current_user["_id"],
        type="warning",
        title="Password changed",
        message="Your password was changed. All sessions were logged out.",
        link="/security/sessions",
    )

    await log_user_action(
        user_id=str(current_user["_id"]),
        action="password_changed",
        entity_type="user",
        entity_id=str(current_user["_id"]),
        details={},
        request=request,
    )

    return {"message": "Password changed successfully. Please log in again."}


@router.get("/me/sessions", response_model=SessionListResponse)
async def list_my_sessions(
    current_user: dict = Depends(get_current_active_user),
    payload: dict = Depends(get_current_token_payload),
):
    sessions = await get_user_sessions(current_user["_id"])
    current_sid = payload.get("sid")
    response_items = [
        SessionInfo(
            session_id=session["session_id"],
            device=session.get("user_agent"),
            ip_address=session.get("ip_address"),
            location=session.get("location"),
            created_at=session["created_at"],
            last_active=session.get("last_active", session["created_at"]),
            expires_at=session["expires_at"],
            is_current=session["session_id"] == current_sid,
        )
        for session in sessions
    ]
    return SessionListResponse(sessions=response_items)


@router.delete("/me/sessions/{session_id}", response_model=dict)
async def revoke_my_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
):
    revoked = await revoke_session(current_user["_id"], session_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    await log_user_action(
        user_id=str(current_user["_id"]),
        action="session_revoked",
        entity_type="session",
        entity_id=session_id,
        details={},
        request=request,
    )
    return {"message": "Session revoked"}


@router.delete("/me/sessions", response_model=dict)
async def revoke_all_other_my_sessions(
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    payload: dict = Depends(get_current_token_payload),
):
    current_sid = payload.get("sid")
    if not current_sid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current session information missing",
        )
    revoked_count = await revoke_all_other_sessions(current_user["_id"], current_sid)
    await log_user_action(
        user_id=str(current_user["_id"]),
        action="all_other_sessions_revoked",
        entity_type="session",
        entity_id=current_sid,
        details={"revoked_count": revoked_count},
        request=request,
    )
    return {"message": "Other sessions revoked", "revoked_count": revoked_count}
