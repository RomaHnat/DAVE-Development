from fastapi import APIRouter, Depends, HTTPException, status, Request
from datetime import timedelta, datetime, timezone
from bson import ObjectId
import threading
import time

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
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from backend.auth.dependencies import get_current_user, get_current_token_payload
from backend.services.session_service import create_session
from backend.services.notification_service import create_notification
from backend.services.token_service import (
    generate_one_time_token,
    verify_one_time_token,
    invalidate_token,
)
from backend.services.email_service import (
    send_welcome_email,
    send_password_reset_email,
)

router = APIRouter(tags=["Authentication"])

ACCESS_TOKEN_EXPIRE_MINUTES = 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

_ip_attempts: dict[str, list[float]] = {}
_ip_lock = threading.Lock()
_IP_RATE_LIMIT = 5
_IP_RATE_WINDOW = 60  # seconds


def _check_ip_rate_limit(ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - _IP_RATE_WINDOW
    with _ip_lock:
        attempts = [t for t in _ip_attempts.get(ip, []) if t > cutoff]
        if len(attempts) >= _IP_RATE_LIMIT:
            _ip_attempts[ip] = attempts
            return False
        attempts.append(now)
        _ip_attempts[ip] = attempts
    return True

@router.get("/")
async def auth_info():
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
async def register_user(payload: UserRegisterRequest, request: Request):
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
        "failed_login_attempts": 0,
        "locked_until": None,
    }

    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    # 4. Generate JWT
    session_id = await create_session(
        user_id=result.inserted_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    access_token = create_access_token(
        data={"sub": str(result.inserted_id), "sid": session_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # 5. Send welcome email (non-blocking – error is swallowed inside)
    await send_welcome_email(email=payload.email, full_name=payload.full_name)

    # 6. Return token + user
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
async def login_user(payload: UserLoginRequest, request: Request):
    # 0. Per-IP rate limit
    ip = request.client.host if request.client else "unknown"
    if not _check_ip_rate_limit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again in a minute.",
        )

    # 1. Find user
    user = await db.users.find_one({"email": payload.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    now = datetime.now(timezone.utc)
    locked_until = user.get("locked_until")
    if locked_until and locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked until {locked_until.isoformat()}",
        )

    # 2. Verify password
    if not verify_password(payload.password, user["password_hash"]):
        failed_attempts = user.get("failed_login_attempts", 0) + 1
        update_data = {"failed_login_attempts": failed_attempts}
        account_locked = False
        if failed_attempts >= MAX_FAILED_ATTEMPTS:
            update_data["locked_until"] = now + timedelta(minutes=LOCKOUT_MINUTES)
            account_locked = True

        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": update_data},
        )

        if account_locked:
            await create_notification(
                user_id=user["_id"],
                type="urgent",
                title="Account temporarily locked",
                message="Too many failed login attempts. Your account is temporarily locked.",
                link="/login",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # 3. Update last_login + reset lockout counters
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "last_login": now,
                "failed_login_attempts": 0,
                "locked_until": None,
            }
        },
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
        "timestamp": now,
    })

    # 5. Create session and generate token
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    session_id = await create_session(
        user_id=user["_id"],
        ip_address=ip_address,
        user_agent=user_agent,
    )

    access_token = create_access_token(
        data={"sub": str(user["_id"]), "sid": session_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    existing_session = await db.user_sessions.find_one(
        {
            "user_id": user["_id"],
            "user_agent": user_agent,
            "is_active": True,
            "session_id": {"$ne": session_id},
        }
    )
    if existing_session is None:
        await create_notification(
            user_id=user["_id"],
            type="warning",
            title="New device login detected",
            message="A new device logged into your account.",
            link="/security/sessions",
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
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        _id=str(current_user["_id"]),
        email=current_user["email"],
        full_name=current_user["full_name"],
        role=current_user["role"],
        created_at=current_user["created_at"],
        phone=current_user.get("phone"),
        is_active=current_user.get("is_active", True),
        is_verified=current_user.get("is_verified", False),
        last_login=current_user.get("last_login"),
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: dict = Depends(get_current_user),
    payload: dict = Depends(get_current_token_payload),
):
    session_id = payload.get("sid")
    access_token = create_access_token(
        data={"sub": str(current_user["_id"]), "sid": session_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_data=UserResponse(
            _id=str(current_user["_id"]),
            email=current_user["email"],
            full_name=current_user["full_name"],
            role=current_user["role"],
            created_at=current_user["created_at"],
            phone=current_user.get("phone"),
            is_active=current_user.get("is_active", True),
            is_verified=current_user.get("is_verified", False),
            last_login=current_user.get("last_login"),
        ),
    )


@router.post("/forgot-password", response_model=dict)
async def forgot_password(payload: ForgotPasswordRequest):

    user = await db.users.find_one({"email": payload.email})
    if user:
        reset_token = await generate_one_time_token(
            user_id=str(user["_id"]),
            token_type="password_reset",
            expires_hours=24,
        )
        await send_password_reset_email(
            email=user["email"],
            full_name=user["full_name"],
            reset_token=reset_token,
        )
    # Always return success to prevent enumeration
    return {
        "message": (
            "If an account with that email exists, a password reset "
            "link has been sent."
        )
    }


@router.post("/reset-password", response_model=dict)
async def reset_password(payload: ResetPasswordRequest):

    token_doc = await verify_one_time_token(payload.token, "password_reset")
    if not token_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    user_id = token_doc["user_id"]
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    new_hash = hash_password(payload.new_password)
    now = datetime.now(timezone.utc)

    # Update password and revoke all existing sessions
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": new_hash, "updated_at": now}},
    )
    await db.user_sessions.update_many(
        {"user_id": user["_id"], "is_active": True},
        {"$set": {"is_active": False, "revoked_at": now}},
    )
    await invalidate_token(payload.token)

    # Audit log
    await db.audit_logs.insert_one({
        "user_id": user["_id"],
        "action": "password_reset",
        "entity_type": "user",
        "entity_id": user["_id"],
        "details": {},
        "ip_address": "unknown",
        "user_agent": "unknown",
        "timestamp": now,
    })

    return {"message": "Password reset successfully. Please log in with your new password."}
