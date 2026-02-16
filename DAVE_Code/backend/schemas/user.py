from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
import re

class UserUpdateRequest(BaseModel):
    """Schema for updating user profile"""
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v is not None and v.strip():
            # Basic phone validation (adjust regex for your region)
            pattern = r'^\+?[\d\s\-()]+$'
            if not re.match(pattern, v):
                raise ValueError('Invalid phone number format')
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "John Doe",
                "phone": "+353 87 123 4567"
            }
        }
    )

class UserDetailResponse(BaseModel):
    """Extended user response with additional details"""
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )
    
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

class UserListItemResponse(BaseModel):
    """Schema for user list item"""
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )
    
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

class UserListResponse(BaseModel):
    """Schema for paginated user list"""
    users: List[UserListItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

class AdminUserDetailResponse(BaseModel):
    """Schema for admin view of user details"""
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )
    
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    recent_activity: List[Dict[str, Any]] = []
    application_count: int = 0
    applications_by_status: Dict[str, int] = {}

class RoleChangeRequest(BaseModel):
    """Schema for changing user role"""
    role: str = Field(..., pattern="^(applicant|admin|super_admin)$")

class ActivityLogResponse(BaseModel):
    """Schema for activity log entry"""
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )
    
    id: str
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime

class ActivityLogListResponse(BaseModel):
    """Schema for paginated activity logs"""
    logs: List[ActivityLogResponse]
    total: int
    page: int
    page_size: int

class AdminActivityLogResponse(BaseModel):
    """Schema for admin view of activity logs"""
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )
    
    id: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime
