from fastapi import APIRouter, Depends, HTTPException, status
from datetime import timedelta, datetime, timezone
from bson import ObjectId

from backend.database import db
from backend.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from backend.auth.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserResponse,
)
from backend.auth.dependencies import get_current_user
from backend.models.user import User

router = APIRouter(tags=["Authentication"])

ACCESS_TOKEN_EXPIRE_MINUTES = 60

@router.get("/")
async def auth_info():
    """Get information about available authentication endpoints."""
    return {
        "message": "Authentication API",
        "endpoints": {
            "register": "POST /api/auth/register",
            "login": "POST /api/auth/login",
            "me": "GET /api/auth/me",
            "refresh": "POST /api/auth/refresh"
        }
    }

@router.post("/register", response_model=TokenResponse)
async def register_user(payload: UserRegisterRequest):
    # 1. Check if email already exists
    existing_user = await db.users.find_one({"email": payload.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # 2. Hash password
    password_hash = hash_password(payload.password)

    # 3. Create user document
    user_doc = {
        "email": payload.email,
        "password_hash": password_hash,
        "full_name": payload.full_name,
        "phone": payload.phone,
        "role": "applicant",
        "is_active": True,
        "is_verified": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    # 4. Generate JWT
    access_token = create_access_token(
        data={"sub": str(result.inserted_id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # 5. Return token + user
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_data=UserResponse(
            _id=str(result.inserted_id),
            email=payload.email,
            full_name=payload.full_name,
            role="applicant",
            created_at=user_doc["created_at"],
        ),
    )

@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLoginRequest):
    # 1. Find user
    user = await db.users.find_one({"email": payload.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # 2. Verify password
    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # 3. Update last_login
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.now(timezone.utc)}},
    )

    # 4. Log audit event
    await db.audit_logs.insert_one({
        "user_id": user["_id"],
        "action": "login",
        "entity_type": "user",
        "entity_id": user["_id"],
        "details": {},
        "ip_address": "unknown",
        "user_agent": "unknown",
        "timestamp": datetime.now(timezone.utc),
    })

    # 5. Generate token
    access_token = create_access_token(
        data={"sub": str(user["_id"])},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_data=UserResponse(
            _id=str(user["_id"]),
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            created_at=user["created_at"],
        ),
    )

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        _id=str(current_user.id) if current_user.id else "",
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        created_at=current_user.created_at,
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(current_user: User = Depends(get_current_user)):
    access_token = create_access_token(
        data={"sub": str(current_user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_data=UserResponse(
            _id=str(current_user.id) if current_user.id else "",
            email=current_user.email,
            full_name=current_user.full_name,
            role=current_user.role,
            created_at=current_user.created_at,
        ),
    )
