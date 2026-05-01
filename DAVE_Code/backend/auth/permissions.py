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
        "manage_own_settings",
        "manage_own_security",
        "manage_own_sessions",
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
        "manage_own_settings",
        "manage_own_security",
        "manage_own_sessions",
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
        "manage_own_settings",
        "manage_own_security",
        "manage_own_sessions",
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
    user_role = user.get("role", "applicant")
    user_permissions = ROLE_PERMISSIONS.get(user_role, [])
    return permission in user_permissions

def get_user_permissions(user: dict) -> List[str]:
    user_role = user.get("role", "applicant")
    return ROLE_PERMISSIONS.get(user_role, [])

def require_role(*allowed_roles: str) -> Callable:
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
