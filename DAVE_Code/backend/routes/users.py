from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId

from backend.auth.dependencies import get_current_active_user
from backend.schemas.user import (
    UserUpdateRequest, 
    UserDetailResponse,
    ActivityLogResponse,
    ActivityLogListResponse
)
from backend.database import db
from backend.services.audit_service import log_user_action, get_user_activity

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/me", response_model=UserDetailResponse)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get current user's profile information.
    Returns:
    User profile with all fields except password_hash
    """
    return UserDetailResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        full_name=current_user["full_name"],
        phone=current_user.get("phone"),
        role=current_user["role"],
        is_active=current_user["is_active"],
        is_verified=current_user.get("is_verified", False),
        created_at=current_user["created_at"],
        updated_at=current_user.get("updated_at"),
        last_login=current_user.get("last_login")
    )

@router.put("/me", response_model=UserDetailResponse)
async def update_user_profile(
    updates: UserUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Update current user's profile.
    Allows updating: full_name, phone
    Email change requires separate endpoint for verification.
    """
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
    
    return UserDetailResponse(
        id=str(updated_user["_id"]),
        email=updated_user["email"],
        full_name=updated_user["full_name"],
        phone=updated_user.get("phone"),
        role=updated_user["role"],
        is_active=updated_user["is_active"],
        is_verified=updated_user.get("is_verified", False),
        created_at=updated_user["created_at"],
        updated_at=updated_user.get("updated_at"),
        last_login=updated_user.get("last_login")
    )

@router.get("/me/activity", response_model=ActivityLogListResponse)
async def get_my_activity(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get current user's activity history.
    Returns paginated list of user's own actions.
    Does not include IP address or user agent for privacy.
    """
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
