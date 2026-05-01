from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

class FormField(BaseModel):
    field_name: str = Field(..., description="Unique key used in form_data dict")
    label: str
    field_type: str = Field(
        ...,
        description="text | number | email | phone | date | dropdown | checkbox | radio",
    )
    is_required: bool = True
    validation: Dict[str, Any] = Field(
        default_factory=dict,
        description="min_length, max_length, pattern, min_value, max_value",
    )
    options: List[str] = Field(default_factory=list, description="For dropdown/radio fields")
    placeholder: Optional[str] = None
    help_text: Optional[str] = None
    order: int = 0
    conditional_display: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Show field only when {field, operator, value} condition is met",
    )


class DocumentRequirement(BaseModel):
    document_type: str = Field(..., description="E.g. 'ID Card', 'Passport'")
    is_mandatory: bool = True
    has_expiry: bool = True
    description: Optional[str] = None
    acceptable_formats: List[str] = Field(default_factory=lambda: ["PDF", "JPG", "PNG"])
    max_file_size_mb: int = 10
    conditional_requirement: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Only required when {field, operator, value} condition is met",
    )


class ValidationRule(BaseModel):
    rule_type: str = Field(
        ...,
        description="required_document | conditional_requirement | data_consistency",
    )
    condition: Dict[str, Any] = Field(default_factory=dict)
    action: Dict[str, Any] = Field(default_factory=dict)
    error_message: str

class ApplicationTypeCreate(BaseModel):
    type_name: str = Field(..., min_length=2, max_length=100)
    description: str = Field(..., min_length=5)
    form_fields: List[FormField] = Field(default_factory=list)
    required_documents: List[DocumentRequirement] = Field(default_factory=list)
    validation_rules: List[ValidationRule] = Field(default_factory=list)


class ApplicationTypeUpdate(BaseModel):
    type_name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    form_fields: Optional[List[FormField]] = None
    required_documents: Optional[List[DocumentRequirement]] = None
    validation_rules: Optional[List[ValidationRule]] = None


class ApplicationTypeSummaryResponse(BaseModel):
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None}
    )
    id: str
    type_name: str
    description: str
    required_docs_count: int
    form_fields_count: int
    status: str


class ApplicationTypeResponse(BaseModel):
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None}
    )
    id: str
    type_name: str
    description: str
    form_fields: List[Dict[str, Any]] = Field(default_factory=list)
    required_documents: List[Dict[str, Any]] = Field(default_factory=list)
    validation_rules: List[Dict[str, Any]] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: datetime
