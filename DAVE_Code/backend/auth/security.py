from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from backend.config import JWT_SECRET_KEY

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    """Hash a plain text password."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None