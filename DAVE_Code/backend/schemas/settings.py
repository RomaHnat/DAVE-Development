from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserSettings(BaseModel):
    language: str = "en"
    timezone: str = "UTC"
    date_format: str = "DD/MM/YYYY"


class UserSettingsResponse(BaseModel):
    settings: UserSettings


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(c.isupper() for c in value):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in value):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one digit")
        return value


class SessionInfo(BaseModel):
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )

    session_id: str
    device: Optional[str] = None
    ip_address: Optional[str] = None
    location: Optional[str] = None
    created_at: datetime
    last_active: datetime
    expires_at: datetime
    is_current: bool = False


class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]


class EmailChangeRequest(BaseModel):
    new_email: str


class EmailChangeConfirmRequest(BaseModel):
    token: str
