from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

_dt_encoder = {datetime: lambda v: v.isoformat() if v else None}


class ApplicationCreate(BaseModel):
    application_type_id: str = Field(..., description="ID of the ApplicationType to use")
    form_data: Dict[str, Any] = Field(default_factory=dict)


class ApplicationUpdate(BaseModel):
    form_data: Dict[str, Any]


class ApplicationPartialUpdate(BaseModel):
    form_data: Optional[Dict[str, Any]] = None


class ApplicationListItem(BaseModel):
    model_config = ConfigDict(json_encoders=_dt_encoder)

    id: str
    case_id: str
    application_type_id: str
    application_type_name: Optional[str] = None
    status: str
    is_editable: bool
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None


class ApplicationDetail(BaseModel):
    model_config = ConfigDict(json_encoders=_dt_encoder)

    id: str
    case_id: str
    application_type_id: str
    application_type_name: Optional[str] = None
    status: str
    is_editable: bool
    form_data: Dict[str, Any] = Field(default_factory=dict)
    validation_results: Dict[str, Any] = Field(default_factory=dict)
    validation_score: float = 0.0
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    admin_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None


class ApplicationListResponse(BaseModel):
    applications: List[ApplicationListItem]
    total: int
    page: int
    page_size: int


class ApplicationTimelineEvent(BaseModel):
    model_config = ConfigDict(json_encoders=_dt_encoder)

    event_type: str
    details: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None
    timestamp: datetime


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    validation_score: float = 0.0
    missing_fields: List[str] = Field(default_factory=list)


class AdminStatusChangeRequest(BaseModel):
    status: str
    notes: Optional[str] = None
