from pydantic import BaseModel, Field
from datetime import datetime, timezone
from bson import ObjectId
from typing import Optional

class Document(BaseModel):
    id: Optional[ObjectId] = Field(alias="_id")
    application_id: ObjectId
    document_type: str
    filename: str
    file_path: str
    file_size: int
    mime_type: str
    status: str = "processing"
    extracted_text: Optional[str] = None
    extracted_entities: list[dict] = []
    expiry_date: Optional[datetime] = None
    confidence_scores: dict = {}
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    ocr_metadata: dict = {}

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True