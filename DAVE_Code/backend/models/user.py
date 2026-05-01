from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime, timezone
from typing import Optional, Dict, Any

class User(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )
    
    id: Optional[str] = Field(None, alias="_id")
    email: EmailStr
    password_hash: str
    full_name: str
    phone: Optional[str] = None
    role: str = "applicant"
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None
    profile_image: Optional[str] = None
    notification_preferences: Dict[str, Any] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=lambda: {
        "language": "en",
        "timezone": "UTC",
        "date_format": "DD/MM/YYYY",
    })
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
