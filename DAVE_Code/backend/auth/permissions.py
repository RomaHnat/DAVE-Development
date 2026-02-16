from typing import List, Dict, Callable
from fastapi import Depends, HTTPException, status

from backend.auth.dependencies import get_current_active_user

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "applicant": [
        "view_own_profile",
        "edit_own_profile",
        "view_own_applications",
        "create_application",
        "edit_own_application",
        "delete_own_application",
        "upload_document",
        "view_own_documents",
        "view_own_notifications",
        "view_own_activity",
    ],
    "admin": [
        # All applicant permissions
        "view_own_profile",
        "edit_own_profile",
        "view_own_applications",
        "create_application",
        "edit_own_application",
        "delete_own_application",
        "upload_document",
        "view_own_documents",
        "view_own_notifications",
        "view_own_activity",
        # Admin-specific permissions
        "view_all_users",
        "view_user_details",
        "activate_user",
        "deactivate_user",
        "view_all_applications",
        "review_application",
        "approve_application",
        "reject_application",
        "request_info",
        "view_application_types",
        "create_application_type",
        "edit_application_type",
        "view_system_activity",
        "view_analytics",
    ],
    "super_admin": [
        # All admin permissions plus:
        "view_own_profile",
        "edit_own_profile",
        "view_own_applications",
        "create_application",
        "edit_own_application",
        "delete_own_application",
        "upload_document",
        "view_own_documents",
        "view_own_notifications",
        "view_own_activity",
        "view_all_users",
        "view_user_details",
        "activate_user",
        "deactivate_user",
        "view_all_applications",
        "review_application",
        "approve_application",
        "reject_application",
        "request_info",
        "view_application_types",
        "create_application_type",
        "edit_application_type",
        "view_system_activity",
        "view_analytics",
        # Super admin only
        "manage_users",
        "change_user_role",
        "delete_user",
        "configure_system",
        "manage_application_types",
    ],
}

def check_permission(user: dict, permission: str) -> bool:
    """
    Check if a user has a specific permission.
    Args:
        user: User document from database
        permission: Permission string to check
    Returns:
        True if user has permission, False otherwise
    """
    user_role = user.get("role", "applicant")
    user_permissions = ROLE_PERMISSIONS.get(user_role, [])
    return permission in user_permissions

def get_user_permissions(user: dict) -> List[str]:
    """
    Get all permissions for a user based on their role.
    Args:
        user: User document from database
    Returns:
        List of permission strings
    """
    user_role = user.get("role", "applicant")
    return ROLE_PERMISSIONS.get(user_role, [])

def require_role(*allowed_roles: str) -> Callable:
    """
    Dependency to check if current user has one of the allowed roles.
    Args:
        *allowed_roles: Variable number of role strings
    Returns:
        Dependency function
    Example:
        @router.get("/admin/users")
        async def get_users(current_user = Depends(require_role("admin", "super_admin"))):
            ...
    """
    async def role_checker(current_user: dict = Depends(get_current_active_user)):
        user_role = current_user.get("role", "applicant")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {' or '.join(allowed_roles)}"
            )
        return current_user
    
    return role_checker

def require_permission(permission: str) -> Callable:
    """
    Dependency to check if current user has a specific permission.
    Args:
        permission: Permission string to require
    Returns:
        Dependency function
    Example:
        @router.get("/applications")
        async def get_applications(current_user = Depends(require_permission("view_all_applications"))):
            ...
    """
    async def permission_checker(current_user: dict = Depends(get_current_active_user)):
        if not check_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required permission: {permission}"
            )
        return current_user
    
    return permission_checker

# Common role dependency shortcuts
require_admin = require_role("admin", "super_admin")
require_super_admin = require_role("super_admin")
