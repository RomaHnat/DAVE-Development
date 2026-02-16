from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId
from backend.auth.security import decode_access_token
from backend.database import db
from backend.models.user import User

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials
    
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Convert ObjectId to string for Pydantic model
    user_doc["_id"] = str(user_doc["_id"])
    return User(**user_doc)

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user (not deactivated)."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )
    return current_user

async def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require user to be an admin."""
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin access required."
        )
    return current_user