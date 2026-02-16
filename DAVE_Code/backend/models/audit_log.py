from pydantic import BaseModel, Field
from datetime import datetime, timezone
from bson import ObjectId
from typing import Optional, Dict


class AuditLog(BaseModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    user_id: Optional[ObjectId] = None
    action: str                       # e.g. "login", "application_submitted"
    entity_type: str                  # e.g. "application", "document"
    entity_id: Optional[ObjectId] = None
    details: Dict = {}                # Extra metadata
    ip_address: str
    user_agent: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
