from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DocumentUploadRequest(BaseModel):
    document_type: str


class DocumentVersionEntry(BaseModel):
    version: int
    gridfs_file_id: str
    filename: str
    file_size: int
    replaced_at: datetime


class DocumentValidationResult(BaseModel):
    # Basic regex/NER-based checks
    name_match: Optional[bool] = None
    name_match_score: Optional[float] = None
    expiry_valid: Optional[bool] = None
    is_expired: Optional[bool] = None
    overall_valid: bool = True
    issues: List[str] = []
    # OpenAI cross-check fields (form data vs document text)
    ai_name_match: Optional[bool] = None
    ai_name_on_document: Optional[str] = None
    ai_expiry_valid: Optional[bool] = None
    ai_expiry_date_found: Optional[str] = None
    ai_verified_fields: Dict[str, Any] = {}
    ai_inconsistencies: List[str] = []
    ai_summary: Optional[str] = None
    # HuggingFace document type verification + key field extraction
    hf_type_verified: Optional[bool] = None
    hf_type_confidence: Optional[float] = None
    hf_detected_as: Optional[str] = None
    hf_extracted_fields: Dict[str, Any] = {}
    hf_field_confidences: Dict[str, float] = {}


class DocumentResponse(BaseModel):
    id: str
    application_id: str
    document_type: str
    filename: str
    file_size: int
    mime_type: str
    status: str
    extracted_text: Optional[str] = None
    extracted_entities: Dict[str, Any] = {}
    expiry_date: Optional[datetime] = None
    confidence_scores: Dict[str, Any] = {}
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    ocr_metadata: Dict[str, Any] = {}
    version_history: List[DocumentVersionEntry] = []
    validation_result: Optional[DocumentValidationResult] = None


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int


class DocumentTypeUpdate(BaseModel):
    document_type: str


class DocumentChecklistItem(BaseModel):
    document_type: str
    is_mandatory: bool
    is_conditional: bool = False
    condition_label: Optional[str] = None
    description: Optional[str] = None
    acceptable_formats: List[str] = []
    max_file_size_mb: int = 10
    uploaded: bool = False
    document_id: Optional[str] = None
    status: Optional[str] = None


class DocumentChecklist(BaseModel):
    application_id: str
    items: List[DocumentChecklistItem]
    total_required: int
    total_uploaded: int
    is_complete: bool
