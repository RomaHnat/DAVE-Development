
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
import math
import re

from backend.auth.permissions import require_admin, require_super_admin
from backend.schemas.user import (
    UserListResponse,
    UserListItemResponse,
    AdminUserDetailResponse,
    RoleChangeRequest,
    AdminActivityLogResponse,
    ActivityLogListResponse,
    AdminActivityLogListResponse,
)
from backend.database import db
from backend.services.audit_service import log_user_action, get_system_activity
from backend.services.notification_service import create_notification
from backend.services.application_service import get_all_applications
from backend.schemas.application import ApplicationListItem, ApplicationListResponse

router = APIRouter(prefix="/admin", tags=["Admin"])

# Admin: List applications — super_admin sees all types; admin is scoped to review_scope
@router.get("/applications", response_model=ApplicationListResponse)
async def list_admin_applications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin)
):
    role = current_user.get("role")
    type_id_filter = None

    if role != "super_admin":
        # Regular admin must have a review_scope
        review_scope = current_user.get("review_scope")
        if not review_scope:
            raise HTTPException(status_code=403, detail="Admin review scope not set.")
        app_type = await db.application_types.find_one(
            {"type_name": {"$regex": re.escape(review_scope), "$options": "i"}}
        )
        if not app_type:
            return ApplicationListResponse(applications=[], total=0, page=page, page_size=page_size)
        type_id_filter = str(app_type["_id"])

    # Fetch applications (all types for super_admin, scoped type for admin)
    apps, total = await get_all_applications(
        page=page,
        page_size=page_size,
        status_filter=status,
        type_id_filter=type_id_filter
    )

    # Batch-resolve application type names
    type_ids = list({a["application_type_id"] for a in apps})
    type_docs = await db.application_types.find({"_id": {"$in": type_ids}}).to_list(length=None)
    type_map = {str(d["_id"]): d["type_name"] for d in type_docs}

    items = [
        ApplicationListItem(
            id=str(a["_id"]),
            case_id=a["case_id"],
            application_type_id=str(a["application_type_id"]),
            application_type_name=type_map.get(str(a["application_type_id"])),
            status=a["status"],
            is_editable=a.get("is_editable", True),
            created_at=a["created_at"],
            updated_at=a["updated_at"],
            submitted_at=a.get("submitted_at")
        ) for a in apps
    ]
    return ApplicationListResponse(applications=items, total=total, page=page, page_size=page_size)

@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    role: Optional[str] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by email or name"),
    current_user: dict = Depends(require_admin)
):
    # Build query
    query = {}
    
    if role:
        query["role"] = role
    
    if is_active is not None:
        query["is_active"] = is_active
    
    if search:
        # Search in email and full_name
        query["$or"] = [
            {"email": {"$regex": search, "$options": "i"}},
            {"full_name": {"$regex": search, "$options": "i"}}
        ]
    
    # Get total count
    total = await db.users.count_documents(query)
    
    # Calculate total pages
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    
    # Get paginated results
    skip = (page - 1) * page_size
    cursor = db.users.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    users = await cursor.to_list(length=page_size)
    
    # Convert to response format
    user_responses = [
        UserListItemResponse(
            id=str(u["_id"]),
            email=u["email"],
            full_name=u["full_name"],
            role=u["role"],
            is_active=u["is_active"],
            created_at=u["created_at"],
            last_login=u.get("last_login")
        )
        for u in users
    ]
    
    return UserListResponse(
        users=user_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)  
async def get_user_details(
    user_id: str,
    current_user: dict = Depends(require_admin)
):
    # Validate ObjectId
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
    
    # Get user
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get recent activity
    recent_logs = await db.audit_logs.find(
        {"user_id": ObjectId(user_id)}
    ).sort("timestamp", -1).limit(10).to_list(length=10)
    
    recent_activity = [
        {
            "action": log["action"],
            "entity_type": log.get("entity_type"),
            "timestamp": log["timestamp"].isoformat() if log.get("timestamp") else None,
            "details": log.get("details")
        }
        for log in recent_logs
    ]
    
    # Get application count and status summary
    app_count = await db.applications.count_documents({"user_id": ObjectId(user_id)})
    
    # Aggregate applications by status
    pipeline = [
        {"$match": {"user_id": ObjectId(user_id)}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    status_counts = await db.applications.aggregate(pipeline).to_list(length=None)
    apps_by_status = {item["_id"]: item["count"] for item in status_counts}
    
    return AdminUserDetailResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user["full_name"],
        phone=user.get("phone"),
        role=user["role"],
        is_active=user["is_active"],
        is_verified=user.get("is_verified", False),
        created_at=user["created_at"],
        updated_at=user.get("updated_at"),
        last_login=user.get("last_login"),
        recent_activity=recent_activity,
        application_count=app_count,
        applications_by_status=apps_by_status
    )

@router.patch("/users/{user_id}/role", response_model=dict)
async def change_user_role(
    user_id: str,
    role_data: RoleChangeRequest,
    request: Request,
    current_user: dict = Depends(require_super_admin)
):
    # Validate ObjectId
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
    
    # Prevent changing own role
    if str(current_user["_id"]) == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role"
        )
    
    # Get target user
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    old_role = user["role"]
    new_role = role_data.role
    
    if old_role == new_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User already has role: {new_role}"
        )
    
    # Update role
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "role": new_role,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )
    
    # Log action
    await log_user_action(
        user_id=str(current_user["_id"]),
        action="role_changed",
        entity_type="user",
        entity_id=user_id,
        details={
            "target_user": user["email"],
            "old_role": old_role,
            "new_role": new_role
        },
        request=request
    )
    
    await create_notification(
        user_id=user["_id"],
        type="info",
        title="Role updated",
        message=f"Your account role has been changed from {old_role} to {new_role}.",
        link="/profile",
    )
    
    return {
        "message": f"User role changed from {old_role} to {new_role}",
        "user_id": user_id,
        "new_role": new_role
    }

@router.patch("/users/{user_id}/status", response_model=dict)
async def toggle_user_status(
    user_id: str,
    request: Request,
    current_user: dict = Depends(require_admin)
):
    # Validate ObjectId
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
    
    # Prevent deactivating own account
    if str(current_user["_id"]) == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    # Get target user
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Toggle is_active status
    new_status = not user["is_active"]
    
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "is_active": new_status,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )
    
    # Log action
    action = "user_activated" if new_status else "user_deactivated"
    await log_user_action(
        user_id=str(current_user["_id"]),
        action=action,
        entity_type="user",
        entity_id=user_id,
        details={
            "target_user": user["email"],
            "new_status": "active" if new_status else "inactive"
        },
        request=request
    )
    
    await create_notification(
        user_id=user["_id"],
        type="warning" if not new_status else "info",
        title="Account status changed",
        message=f"Your account is now {'active' if new_status else 'inactive'}.",
        link="/profile",
    )
    
    status_text = "activated" if new_status else "deactivated"
    return {
        "message": f"User account {status_text}",
        "user_id": user_id,
        "is_active": new_status
    }

@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: str,
    request: Request,
    current_user: dict = Depends(require_super_admin)
):
    # Validate ObjectId
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
    
    # Prevent deleting own account
    if str(current_user["_id"]) == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    # Get target user
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check for active applications under review
    active_app_count = await db.applications.count_documents({
        "user_id": ObjectId(user_id),
        "status": {"$in": ["submitted", "under_review"]}
    })
    
    if active_app_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete user with {active_app_count} active application(s) under review"
        )
    
    # Perform soft delete
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )
    
    # Log action
    await log_user_action(
        user_id=str(current_user["_id"]),
        action="user_deleted",
        entity_type="user",
        entity_id=user_id,
        details={
            "target_user": user["email"],
            "deletion_type": "soft_delete"
        },
        request=request
    )
    
    await create_notification(
        user_id=user["_id"],
        type="urgent",
        title="Account access removed",
        message="Your account has been deactivated by an administrator.",
        link="/support",
    )
    
    return {
        "message": "User account deleted successfully",
        "user_id": user_id
    }

@router.get("/activity-logs", response_model=AdminActivityLogListResponse)
async def get_system_activity_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    current_user: dict = Depends(require_admin)
):
    logs, total = await get_system_activity(
        page=page,
        page_size=page_size,
        user_id=user_id,
        action=action,
        entity_type=entity_type
    )
    
    # Convert logs to response format (include IP and user agent for admins)
    activity_responses = [
        AdminActivityLogResponse(
            id=str(log["_id"]),
            user_id=str(log["user_id"]) if log.get("user_id") else None,
            user_email=log.get("user_email"),
            action=log["action"],
            entity_type=log.get("entity_type"),
            entity_id=str(log["entity_id"]) if log.get("entity_id") else None,
            details=log.get("details"),
            ip_address=log.get("ip_address"),
            user_agent=log.get("user_agent"),
            timestamp=log["timestamp"]
        )
        for log in logs
    ]
    
    return AdminActivityLogListResponse(
        logs=activity_responses,
        total=total,
        page=page,
        page_size=page_size
    )
