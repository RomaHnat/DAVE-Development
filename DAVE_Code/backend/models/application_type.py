from pydantic import BaseModel, Field
from datetime import datetime, timezone
from bson import ObjectId
from typing import Optional, List, Dict


class ApplicationType(BaseModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    type_name: str  # e.g. "SUSI Grant"
    description: str
    form_fields: List[Dict] = []          # Dynamic form schema
    required_documents: List[Dict] = []   # Document requirements
    validation_rules: List[Dict] = []     # Conditional logic
    status: str = "active"                # "active" | "inactive"
    created_by: ObjectId                 
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
