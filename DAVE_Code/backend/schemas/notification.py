from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )

    id: str
    type: str
    title: str
    message: str
    link: Optional[str] = None
    is_read: bool
    created_at: datetime
    expires_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class NotificationPreferencesUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    preferences: Optional[dict] = Field(
        default=None,
        description="Per-event channel preferences",
    )


class NotificationPreferencesResponse(BaseModel):
    email_enabled: bool
    preferences: dict
