from pydantic import BaseModel, Field
from datetime import datetime, timezone
from bson import ObjectId
from typing import Optional


class Notification(BaseModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    user_id: ObjectId
    type: str = "info"        # "info" | "warning" | "urgent" | "success"
    title: str
    message: str
    link: Optional[str] = None
    is_read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
