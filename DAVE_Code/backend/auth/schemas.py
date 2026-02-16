from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from datetime import datetime
from typing import Optional

class UserRegisterRequest(BaseModel):
    """Schema for user registration."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)
    phone: Optional[str] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

class UserLoginRequest(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    """Schema for user response."""
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )
    
    id: str = Field(alias="_id")
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime
    last_login: Optional[datetime] = None

class TokenResponse(BaseModel):
    """Schema for token response."""
    access_token: str
    token_type: str
    user_data: UserResponse
