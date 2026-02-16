from pydantic import BaseModel, Field
from datetime import datetime, timezone
from bson import ObjectId
from typing import Optional

class Application(BaseModel):
    id: Optional[ObjectId] = Field(alias="_id")
    case_id: str
    user_id: ObjectId
    application_type_id: ObjectId
    status: str = "draft"
    form_data: dict = {}
    validation_results: dict = {}
    validation_score: float = 0.0
    recommendations: list[dict] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: Optional[datetime] = None
    reviewed_by: Optional[ObjectId] = None
    reviewed_at: Optional[datetime] = None
    admin_notes: Optional[str] = None
    is_editable: bool = True

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
