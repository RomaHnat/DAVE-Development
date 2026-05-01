from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from backend.database import db
from backend.services.gridfs_service import (
    delete_file_from_gridfs,
    download_file_from_gridfs,
    upload_file_to_gridfs,
)
from backend.services.file_validation_service import (
    MAX_FILES_PER_APPLICATION,
    validate_upload,
)

def _doc_to_dict(doc: dict) -> dict:

    doc["id"] = str(doc.pop("_id"))
    doc["application_id"] = str(doc["application_id"])
    return doc


async def _assert_application_editable(application_id: ObjectId, user_id: ObjectId) -> None:

    app = await db.applications.find_one({"_id": application_id})
    if app is None:
        raise ValueError("Application not found")
    if app["user_id"] != user_id:
        raise PermissionError("You do not own this application")
    if not app.get("is_editable", True):
        raise ValueError("This application is no longer editable")

async def upload_document(
    application_id: str,
    user_id: str,
    filename: str,
    file_data: bytes,
    document_type: str,
    mime_type: str,
) -> dict:

    app_oid = ObjectId(application_id)
    user_oid = ObjectId(user_id)

    await _assert_application_editable(app_oid, user_oid)

    # File validation
    is_valid, errors = validate_upload(filename, file_data)
    if not is_valid:
        raise ValueError("; ".join(errors))

    # Enforce per-application file cap
    count = await db.documents.count_documents({"application_id": app_oid})
    if count >= MAX_FILES_PER_APPLICATION:
        raise ValueError(
            f"Maximum of {MAX_FILES_PER_APPLICATION} documents per application reached."
        )

    # Store binary in GridFS
    file_id = await upload_file_to_gridfs(
        file_data,
        filename,
        metadata={
            "application_id": application_id,
            "document_type": document_type,
            "user_id": user_id,
        },
    )

    now = datetime.now(timezone.utc)
    doc = {
        "application_id": app_oid,
        "document_type": document_type,
        "filename": filename,
        "gridfs_file_id": file_id,
        "file_size": len(file_data),
        "mime_type": mime_type,
        "status": "processing",
        "extracted_text": None,
        "extracted_entities": {},
        "expiry_date": None,
        "confidence_scores": {},
        "uploaded_at": now,
        "processed_at": None,
        "ocr_metadata": {},
    }

    result = await db.documents.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_dict(doc)

async def get_application_documents(
    application_id: str,
    user_id: str,
    role: str = "applicant",
) -> List[dict]:

    app_oid = ObjectId(application_id)

    if role not in ("admin", "super_admin"):
        app = await db.applications.find_one({"_id": app_oid, "user_id": ObjectId(user_id)})
        if app is None:
            raise PermissionError("Application not found or access denied")

    docs = await db.documents.find({"application_id": app_oid}).to_list(None)
    return [_doc_to_dict(d) for d in docs]


async def get_document_by_id(document_id: str, user_id: str, role: str = "applicant") -> dict:

    doc = await db.documents.find_one({"_id": ObjectId(document_id)})
    if doc is None:
        raise FileNotFoundError("Document not found")

    if role not in ("admin", "super_admin"):
        app = await db.applications.find_one(
            {"_id": doc["application_id"], "user_id": ObjectId(user_id)}
        )
        if app is None:
            raise PermissionError("Access denied")

    return _doc_to_dict(doc)

async def download_document(document_id: str, user_id: str, role: str = "applicant") -> Tuple[bytes, str, str]:

    doc = await get_document_by_id(document_id, user_id, role)
    file_data = await download_file_from_gridfs(doc["gridfs_file_id"])
    return file_data, doc["filename"], doc["mime_type"]

async def replace_document(
    document_id: str,
    user_id: str,
    filename: str,
    file_data: bytes,
    mime_type: str,
) -> dict:
    doc_oid = ObjectId(document_id)
    doc = await db.documents.find_one({"_id": doc_oid})
    if doc is None:
        raise FileNotFoundError("Document not found")

    app = await db.applications.find_one(
        {"_id": doc["application_id"], "user_id": ObjectId(user_id)}
    )
    if app is None:
        raise PermissionError("Access denied")
    if not app.get("is_editable", True):
        raise ValueError("Cannot replace documents in a non-editable application")

    is_valid, errors = validate_upload(filename, file_data)
    if not is_valid:
        raise ValueError("; ".join(errors))

    # Archive current version before overwriting
    version_entry = {
        "version": len(doc.get("version_history", [])) + 1,
        "gridfs_file_id": doc["gridfs_file_id"],
        "filename": doc["filename"],
        "file_size": doc["file_size"],
        "replaced_at": datetime.now(timezone.utc),
    }

    new_file_id = await upload_file_to_gridfs(
        file_data,
        filename,
        metadata={
            "application_id": str(doc["application_id"]),
            "document_type": doc["document_type"],
            "user_id": user_id,
        },
    )

    now = datetime.now(timezone.utc)
    await db.documents.update_one(
        {"_id": doc_oid},
        {
            "$set": {
                "gridfs_file_id": new_file_id,
                "filename": filename,
                "file_size": len(file_data),
                "mime_type": mime_type,
                "status": "processing",
                "extracted_text": None,
                "extracted_entities": {},
                "expiry_date": None,
                "confidence_scores": {},
                "ocr_metadata": {},
                "uploaded_at": now,
                "processed_at": None,
            },
            "$push": {"version_history": version_entry},
        },
    )

    updated = await db.documents.find_one({"_id": doc_oid})
    return _doc_to_dict(updated)


async def delete_document(document_id: str, user_id: str, role: str = "applicant") -> None:
    doc_oid = ObjectId(document_id)
    doc = await db.documents.find_one({"_id": doc_oid})
    if doc is None:
        raise FileNotFoundError("Document not found")

    if role not in ("admin", "super_admin"):
        app = await db.applications.find_one(
            {"_id": doc["application_id"], "user_id": ObjectId(user_id)}
        )
        if app is None:
            raise PermissionError("Access denied")
        if not app.get("is_editable", True):
            raise ValueError("Cannot delete documents from a non-editable application")

    await delete_file_from_gridfs(doc["gridfs_file_id"])
    await db.documents.delete_one({"_id": doc_oid})

async def update_document_type(document_id: str, user_id: str, new_type: str) -> dict:

    doc_oid = ObjectId(document_id)
    doc = await db.documents.find_one({"_id": doc_oid})
    if doc is None:
        raise FileNotFoundError("Document not found")

    app = await db.applications.find_one(
        {"_id": doc["application_id"], "user_id": ObjectId(user_id)}
    )
    if app is None:
        raise PermissionError("Access denied")

    await db.documents.update_one(
        {"_id": doc_oid},
        {"$set": {"document_type": new_type}},
    )
    doc["document_type"] = new_type
    return _doc_to_dict(doc)

async def save_ocr_results(document_id: str, ocr_data: Dict[str, Any]) -> None:

    await db.documents.update_one(
        {"_id": ObjectId(document_id)},
        {
            "$set": {
                "status": ocr_data.get("status", "processed"),
                "extracted_text": ocr_data.get("extracted_text"),
                "extracted_entities": ocr_data.get("extracted_entities", {}),
                "expiry_date": ocr_data.get("expiry_date"),
                "confidence_scores": ocr_data.get("confidence_scores", {}),
                "ocr_metadata": ocr_data.get("ocr_metadata", {}),
                "processed_at": datetime.now(timezone.utc),
                "processing_step": None,  # clear step once OCR is done
            }
        },
    )


async def set_processing_step(document_id: str, step: str) -> None:
    await db.documents.update_one(
        {"_id": ObjectId(document_id)},
        {"$set": {"processing_step": step}},
    )

def _evaluate_condition(condition: Dict[str, Any], form_data: Dict[str, Any]) -> bool:

    if not condition:
        return True
    field    = condition.get("field", "")
    operator = condition.get("operator", "equals")
    value    = condition.get("value")

    actual = form_data.get(field)
    if actual is None:
        return False

    actual_str = str(actual).strip().lower()
    if isinstance(value, str):
        value_cmp = value.strip().lower()
    else:
        value_cmp = value  # list or other type

    if operator in ("equals", "eq"):
        return actual_str == value_cmp
    if operator in ("not_equals", "ne", "neq"):
        return actual_str != value_cmp
    if operator == "in":
        return actual_str in [str(v).strip().lower() for v in (value_cmp or [])]
    if operator == "not_in":
        return actual_str not in [str(v).strip().lower() for v in (value_cmp or [])]
    if operator == "contains":
        return value_cmp in actual_str
    # Unknown operator — default to True so we err on the side of inclusion
    return True


async def get_document_checklist(application_id: str, user_id: str, role: str = "applicant") -> dict:

    app_oid = ObjectId(application_id)

    if role not in ("admin", "super_admin"):
        app = await db.applications.find_one({"_id": app_oid, "user_id": ObjectId(user_id)})
    else:
        app = await db.applications.find_one({"_id": app_oid})

    if app is None:
        raise FileNotFoundError("Application not found")

    form_data: Dict[str, Any] = app.get("form_data") or {}

    app_type = await db.application_types.find_one({"_id": app["application_type_id"]})
    required_docs: List[Dict[str, Any]] = (app_type or {}).get("required_documents", [])

    uploaded = await db.documents.find({"application_id": app_oid}).to_list(None)
    uploaded_by_type: Dict[str, dict] = {d["document_type"]: d for d in uploaded}

    items = []
    mandatory_count = 0

    for req in required_docs:
        doc_type = req.get("document_type", "")

        condition = req.get("conditional_requirement")
        is_conditional = bool(condition)
        if is_conditional:
            # Only include in checklist when the condition is met
            if not _evaluate_condition(condition, form_data):
                continue

        is_mandatory = req.get("is_mandatory", True)
        if is_mandatory:
            mandatory_count += 1

        uploaded_doc = uploaded_by_type.get(doc_type)
        item: Dict[str, Any] = {
            "document_type": doc_type,
            "is_mandatory": is_mandatory,
            "is_conditional": is_conditional,
            "condition_label": _condition_label(condition) if is_conditional else None,
            "description": req.get("description"),
            "acceptable_formats": req.get("acceptable_formats", ["PDF", "JPG", "PNG"]),
            "max_file_size_mb": req.get("max_file_size_mb", 10),
            "uploaded": uploaded_doc is not None,
            "document_id": str(uploaded_doc["_id"]) if uploaded_doc else None,
            "status": uploaded_doc.get("status") if uploaded_doc else None,
            "processing_step": uploaded_doc.get("processing_step") if uploaded_doc else None,
            "validation_result": uploaded_doc.get("validation_result") if uploaded_doc else None,
        }
        items.append(item)

    mandatory_uploaded = sum(
        1 for item in items if item["is_mandatory"] and item["uploaded"]
    )

    return {
        "application_id": application_id,
        "items": items,
        "total_required": mandatory_count,
        "total_uploaded": mandatory_uploaded,
        "is_complete": mandatory_uploaded >= mandatory_count,
    }


def _condition_label(condition: Optional[Dict[str, Any]]) -> Optional[str]:
    
    if not condition:
        return None
    field    = condition.get("field", "")
    operator = condition.get("operator", "equals")
    value    = condition.get("value", "")
    op_map   = {
        "equals":     "is",
        "not_equals": "is not",
        "in":         "is one of",
        "not_in":     "is not one of",
        "contains":   "contains",
    }
    op_label = op_map.get(operator, operator)
    val_str  = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
    return f"Required when {field.replace('_', ' ')} {op_label} {val_str}"
