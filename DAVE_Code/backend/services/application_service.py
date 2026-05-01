from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from pymongo import ReturnDocument

from backend.database import db

# Transitions that users are allowed to make
USER_VALID_TRANSITIONS: Dict[str, List[str]] = {
    "draft": ["pending", "ready"],
    "pending": ["draft", "ready"],
    "ready": ["pending"],
    # Users submit via dedicated submit endpoint, not directly via PATCH
}

# Transitions that admins are allowed to make
ADMIN_VALID_TRANSITIONS: Dict[str, List[str]] = {
    "submitted": ["under_review"],
    "under_review": ["approved", "rejected", "pending_info"],
    "pending_info": ["under_review"],
}

async def _next_sequence(year: int) -> int:
    counter = await db.counters.find_one_and_update(
        {"_id": f"case_id_{year}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return counter["seq"]


async def generate_case_id() -> str:
    year = datetime.now(timezone.utc).year
    seq = await _next_sequence(year)
    return f"DAVE-{year}-{seq:04d}"

async def _add_timeline_event(
    application_id: ObjectId,
    event_type: str,
    details: Optional[Dict[str, Any]] = None,
    user_id: Optional[ObjectId] = None,
) -> None:
    await db.application_events.insert_one(
        {
            "application_id": application_id,
            "event_type": event_type,
            "details": details or {},
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc),
        }
    )

async def create_application(
    user_id: ObjectId,
    type_id: str,
    form_data: Dict[str, Any],
) -> dict:
    # Prevent duplicate active applications of the same type for this user
    existing = await db.applications.find_one({
        "user_id": user_id,
        "application_type_id": ObjectId(type_id),
        "status": {"$nin": ["withdrawn", "rejected"]},
    })
    if existing:
        app_type = await db.application_types.find_one({"_id": ObjectId(type_id)})
        type_name = (app_type or {}).get("name", "this application type")
        raise ValueError(
            f"You already have an active application for '{type_name}' "
            f"(Case ID: {existing['case_id']}). "
            f"You cannot start a duplicate."
        )

    case_id = await generate_case_id()
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        "case_id": case_id,
        "user_id": user_id,
        "application_type_id": ObjectId(type_id),
        "status": "draft",
        "form_data": form_data,
        "validation_results": {},
        "validation_score": 0.0,
        "recommendations": [],
        "is_editable": True,
        "admin_notes": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "submitted_at": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.applications.insert_one(doc)
    doc["_id"] = result.inserted_id
    await _add_timeline_event(result.inserted_id, "created", user_id=user_id)
    return doc


async def get_user_applications(
    user_id: ObjectId,
    page: int = 1,
    page_size: int = 10,
    status_filter: Optional[str] = None,
    sort_by: str = "updated_at",
) -> Tuple[List[dict], int]:
    query: Dict[str, Any] = {"user_id": user_id}
    if status_filter:
        query["status"] = status_filter
    total = await db.applications.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.applications.find(query).sort(sort_by, -1).skip(skip).limit(page_size)
    apps = await cursor.to_list(length=page_size)
    return apps, total


async def get_all_applications(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    user_id_filter: Optional[str] = None,
    type_id_filter: Optional[str] = None,
) -> Tuple[List[dict], int]:
    query: Dict[str, Any] = {}
    if status_filter:
        query["status"] = status_filter
    if user_id_filter and ObjectId.is_valid(user_id_filter):
        query["user_id"] = ObjectId(user_id_filter)
    if type_id_filter and ObjectId.is_valid(type_id_filter):
        query["application_type_id"] = ObjectId(type_id_filter)
    total = await db.applications.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.applications.find(query).sort("updated_at", -1).skip(skip).limit(page_size)
    apps = await cursor.to_list(length=page_size)
    return apps, total


async def get_application_by_id(
    app_id: str,
    user_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    if not ObjectId.is_valid(app_id):
        return None
    query: Dict[str, Any] = {"_id": ObjectId(app_id)}
    if user_id is not None:
        query["user_id"] = user_id
    return await db.applications.find_one(query)


async def update_application(
    app_id: str,
    form_data: Dict[str, Any],
    user_id: ObjectId,
    partial: bool = False,
) -> Optional[dict]:
    if not ObjectId.is_valid(app_id):
        return None

    app = await db.applications.find_one(
        {"_id": ObjectId(app_id), "user_id": user_id, "is_editable": True}
    )
    if not app:
        return None

    # Merge vs replace
    if partial:
        merged = {**app.get("form_data", {}), **form_data}
    else:
        merged = form_data

    # Determine new status based on validation
    app_type = await db.application_types.find_one(
        {"_id": app["application_type_id"]}
    )
    new_status = "pending"
    if app_type:
        from backend.services.form_service import validate_form_data
        errors = validate_form_data(merged, app_type.get("form_fields", []))
        if not errors:
            new_status = "ready"

    now = datetime.now(timezone.utc)
    await db.applications.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {"form_data": merged, "status": new_status, "updated_at": now}},
    )
    await _add_timeline_event(ObjectId(app_id), "updated", user_id=user_id)
    return await db.applications.find_one({"_id": ObjectId(app_id)})


async def delete_application(app_id: str, user_id: ObjectId) -> bool:
    if not ObjectId.is_valid(app_id):
        return False
    result = await db.applications.delete_one(
        {"_id": ObjectId(app_id), "user_id": user_id, "status": {"$in": ["draft", "ready"]}}
    )
    return result.deleted_count > 0


async def submit_application(
    app_id: str,
    user_id: ObjectId,
) -> Tuple[bool, List[str], Optional[dict]]:

    app = await db.applications.find_one(
        {"_id": ObjectId(app_id), "user_id": user_id}
    )
    if not app:
        return False, ["Application not found"], None
    if app["status"] not in ("draft", "pending", "ready"):
        return False, [
            f"Cannot submit an application with status '{app['status']}'"
        ], None

    # Final form validation
    app_type = await db.application_types.find_one(
        {"_id": app["application_type_id"]}
    )
    if not app_type:
        return False, ["Application type not found"], None

    from backend.services.form_service import validate_form_data, calculate_validation_score
    errors = validate_form_data(app.get("form_data", {}), app_type.get("form_fields", []))
    if errors:
        return False, errors, None

    # Check required documents are uploaded and have passed validation
    from backend.services.document_service import _evaluate_condition
    required_docs = app_type.get("required_documents", [])
    form_data = app.get("form_data") or {}

    # Build a map of document_type → best document (prefer validated > validated_with_issues > others)
    _status_rank = {"validated": 0, "validated_with_issues": 1, "processing_failed": 2, "processed": 3, "processing": 4}
    uploaded_docs: Dict[str, dict] = {}
    for d in await db.documents.find({"application_id": ObjectId(app_id)}).to_list(None):
        dt = d.get("document_type", "")
        existing = uploaded_docs.get(dt)
        if existing is None or _status_rank.get(d.get("status", ""), 99) < _status_rank.get(existing.get("status", ""), 99):
            uploaded_docs[dt] = d

    missing_docs: List[str] = []
    invalid_docs: List[str] = []
    pending_docs: List[str] = []

    for req in required_docs:
        if not req.get("is_mandatory", True):
            continue
        condition = req.get("conditional_requirement")
        if condition and not _evaluate_condition(condition, form_data):
            continue  # conditional doc not triggered
        doc_type = req.get("document_type", "")
        doc = uploaded_docs.get(doc_type)
        if doc is None:
            missing_docs.append(doc_type)
            continue
        status = doc.get("status", "")
        if status in ("processing", "processed"):
            pending_docs.append(doc_type)
        elif status in ("processing_failed",):
            invalid_docs.append(f"{doc_type} (processing failed — please re-upload)")
        elif status == "validated_with_issues":
            invalid_docs.append(f"{doc_type} (document did not pass verification — please re-upload)")

    errors: List[str] = []
    if missing_docs:
        errors.append(
            f"Missing required document(s): {', '.join(missing_docs)}. "
            f"Please upload them before submitting."
        )
    if pending_docs:
        errors.append(
            f"Document(s) still being processed: {', '.join(pending_docs)}. "
            f"Please wait for validation to complete before submitting."
        )
    if invalid_docs:
        errors.append(
            f"The following document(s) failed verification: {'; '.join(invalid_docs)}."
        )
    if errors:
        return False, errors, None

    score = calculate_validation_score(
        app.get("form_data", {}), app_type.get("form_fields", [])
    )
    now = datetime.now(timezone.utc)
    await db.applications.update_one(
        {"_id": ObjectId(app_id)},
        {
            "$set": {
                "status": "submitted",
                "submitted_at": now,
                "is_editable": False,
                "validation_score": score,
                "updated_at": now,
            }
        },
    )
    await _add_timeline_event(
        ObjectId(app_id), "submitted",
        details={"validation_score": score},
        user_id=user_id,
    )
    updated = await db.applications.find_one({"_id": ObjectId(app_id)})
    return True, [], updated


async def admin_change_status(
    app_id: str,
    new_status: str,
    admin_user_id: ObjectId,
    notes: Optional[str] = None,
) -> Tuple[bool, str, Optional[dict]]:

    if not ObjectId.is_valid(app_id):
        return False, "Invalid application ID", None
    app = await db.applications.find_one({"_id": ObjectId(app_id)})
    if not app:
        return False, "Application not found", None
    current_status = app["status"]

    allowed_next = ADMIN_VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed_next:
        return (
            False,
            f"Cannot transition '{current_status}' → '{new_status}'. "
            f"Allowed: {allowed_next}",
            None,
        )

    now = datetime.now(timezone.utc)
    update_fields: Dict[str, Any] = {
        "status": new_status,
        "updated_at": now,
        "reviewed_by": admin_user_id,
        "reviewed_at": now,
    }
    if notes is not None:
        update_fields["admin_notes"] = notes
    # Lock editing if now under review or terminal
    if new_status in ("under_review", "approved", "rejected"):
        update_fields["is_editable"] = False
    # Re-enable editing if pending_info so user can update
    if new_status == "pending_info":
        update_fields["is_editable"] = True

    await db.applications.update_one(
        {"_id": ObjectId(app_id)}, {"$set": update_fields}
    )
    await _add_timeline_event(
        ObjectId(app_id),
        "status_changed",
        details={"from": current_status, "to": new_status, "notes": notes},
        user_id=admin_user_id,
    )
    updated = await db.applications.find_one({"_id": ObjectId(app_id)})

    # Notify applicant
    try:
        from backend.services.notification_service import create_notification
        applicant_id = updated["user_id"]
        title = f"Application status updated: {new_status.replace('_', ' ').title()}"
        msg = f"Your application (Case ID: {updated['case_id']}) status changed from {current_status} to {new_status}."
        if notes:
            msg += f"\n\nAdmin notes: {notes}"
        await create_notification(
            user_id=applicant_id,
            type="application_status_changed",
            title=title,
            message=msg,
            link=f"/application.html?id={str(updated['_id'])}",
            send_email_if_enabled=True,
        )
    except Exception as exc:
        import logging
        logging.warning(f"Failed to send status notification: {exc}")

    return True, "", updated


async def get_application_timeline(app_id: str) -> List[dict]:
    if not ObjectId.is_valid(app_id):
        return []
    cursor = db.application_events.find(
        {"application_id": ObjectId(app_id)}
    ).sort("timestamp", 1)
    return await cursor.to_list(length=None)
