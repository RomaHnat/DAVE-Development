import math
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from backend.auth.dependencies import get_current_active_user
from backend.auth.permissions import require_admin
from backend.database import db
from backend.schemas.application import (
    AdminStatusChangeRequest,
    ApplicationCreate,
    ApplicationDetail,
    ApplicationListItem,
    ApplicationListResponse,
    ApplicationPartialUpdate,
    ApplicationTimelineEvent,
    ApplicationUpdate,
    ValidationResult,
)
from backend.services.application_service import (
    admin_change_status,
    create_application,
    delete_application,
    get_all_applications,
    get_application_by_id,
    get_application_timeline,
    get_user_applications,
    submit_application,
    update_application,
)
from backend.services.form_service import (
    calculate_validation_score,
    get_required_documents,
    validate_form_data,
)
from backend.services.notification_service import create_notification

router = APIRouter(tags=["Applications"])

async def _type_name(type_id: ObjectId) -> Optional[str]:
    app_type = await db.application_types.find_one(
        {"_id": type_id}, {"type_name": 1}
    )
    return app_type["type_name"] if app_type else None


def _to_list_item(app: dict, type_name: Optional[str] = None) -> ApplicationListItem:
    return ApplicationListItem(
        id=str(app["_id"]),
        case_id=app["case_id"],
        application_type_id=str(app["application_type_id"]),
        application_type_name=type_name,
        status=app["status"],
        is_editable=app.get("is_editable", True),
        created_at=app["created_at"],
        updated_at=app["updated_at"],
        submitted_at=app.get("submitted_at"),
    )


def _to_detail(app: dict, type_name: Optional[str] = None) -> ApplicationDetail:
    return ApplicationDetail(
        id=str(app["_id"]),
        case_id=app["case_id"],
        application_type_id=str(app["application_type_id"]),
        application_type_name=type_name,
        status=app["status"],
        is_editable=app.get("is_editable", True),
        form_data=app.get("form_data", {}),
        validation_results=app.get("validation_results", {}),
        validation_score=app.get("validation_score", 0.0),
        recommendations=app.get("recommendations", []),
        admin_notes=app.get("admin_notes"),
        created_at=app["created_at"],
        updated_at=app["updated_at"],
        submitted_at=app.get("submitted_at"),
        reviewed_at=app.get("reviewed_at"),
    )

@router.post("/applications", response_model=ApplicationDetail, status_code=status.HTTP_201_CREATED)
async def create_new_application(
    data: ApplicationCreate,
    current_user: dict = Depends(get_current_active_user),
):
    # Verify the application type exists and is active
    if not ObjectId.is_valid(data.application_type_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid application_type_id",
        )
    app_type = await db.application_types.find_one(
        {"_id": ObjectId(data.application_type_id), "status": "active"}
    )
    if not app_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application type not found or inactive",
        )

    try:
        app = await create_application(
            user_id=current_user["_id"],
            type_id=data.application_type_id,
            form_data=data.form_data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return _to_detail(app, type_name=app_type["type_name"])


@router.get("/applications", response_model=ApplicationListResponse)
async def list_my_applications(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    status_filter: Optional[str] = Query(None, alias="status"),
    sort_by: str = Query("updated_at", pattern="^(created_at|updated_at|submitted_at)$"),
    current_user: dict = Depends(get_current_active_user),
):
    apps, total = await get_user_applications(
        user_id=current_user["_id"],
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        sort_by=sort_by,
    )

    # Batch-fetch type names to avoid N+1 queries
    type_ids = list({a["application_type_id"] for a in apps if a.get("application_type_id")})
    type_map: dict = {}
    if type_ids:
        cursor = db.application_types.find(
            {"_id": {"$in": [ObjectId(tid) if not isinstance(tid, ObjectId) else tid for tid in type_ids]}},
            {"type_name": 1},
        )
        async for doc in cursor:
            type_map[str(doc["_id"])] = doc["type_name"]

    items = [
        _to_list_item(a, type_name=type_map.get(str(a["application_type_id"])))
        for a in apps
    ]
    return ApplicationListResponse(
        applications=items, total=total, page=page, page_size=page_size
    )


@router.post("/applications/validate", response_model=ValidationResult)
async def validate_form_for_type(
    data: ApplicationCreate,
    current_user: dict = Depends(get_current_active_user),
):
    """Validate form data against an application type without creating a full application."""
    if not ObjectId.is_valid(data.application_type_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid application_type_id",
        )
    app_type = await db.application_types.find_one(
        {"_id": ObjectId(data.application_type_id), "status": "active"}
    )
    if not app_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application type not found or inactive",
        )

    form_fields = app_type.get("form_fields", [])
    form_data = data.form_data
    errors = validate_form_data(form_data, form_fields)
    score = calculate_validation_score(form_data, form_fields)

    missing = [
        f["field_name"]
        for f in form_fields
        if f.get("is_required", False)
        and (
            form_data.get(f["field_name"]) is None
            or str(form_data[f["field_name"]]).strip() == ""
        )
    ]

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        validation_score=score,
        missing_fields=missing,
    )


@router.get("/applications/{app_id}", response_model=ApplicationDetail)
async def get_my_application(
    app_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    app = await get_application_by_id(app_id, user_id=current_user["_id"])
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    tname = await _type_name(app["application_type_id"])
    return _to_detail(app, type_name=tname)


@router.put("/applications/{app_id}", response_model=ApplicationDetail)
async def update_my_application(
    app_id: str,
    data: ApplicationUpdate,
    current_user: dict = Depends(get_current_active_user),
):
    updated = await update_application(
        app_id=app_id,
        form_data=data.form_data,
        user_id=current_user["_id"],
        partial=False,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found, not owned by you, or not editable",
        )
    tname = await _type_name(updated["application_type_id"])
    return _to_detail(updated, type_name=tname)


@router.patch("/applications/{app_id}", response_model=ApplicationDetail)
async def patch_my_application(
    app_id: str,
    data: ApplicationPartialUpdate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
):
    if data.form_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to update",
        )
    updated = await update_application(
        app_id=app_id,
        form_data=data.form_data,
        user_id=current_user["_id"],
        partial=True,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found, not owned by you, or not editable",
        )

    # Re-validate all documents that already have OCR data — form data just changed
    # and name / DOB comparison must be re-run against the new values.
    from backend.tasks.document_tasks import revalidate_document
    revalidatable_statuses = ["processed", "validated", "validated_with_issues"]
    cursor = db.documents.find(
        {"application_id": updated["_id"], "status": {"$in": revalidatable_statuses}}
    )
    async for doc in cursor:
        background_tasks.add_task(revalidate_document, str(doc["_id"]))

    tname = await _type_name(updated["application_type_id"])
    return _to_detail(updated, type_name=tname)


@router.delete("/applications/{app_id}", response_model=dict)
async def delete_my_application(
    app_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    deleted = await delete_application(app_id, current_user["_id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found or cannot be deleted (only 'draft' or 'ready' applications can be deleted)",
        )
    return {"message": "Application deleted"}

@router.post("/applications/{app_id}/submit", response_model=ApplicationDetail)
async def submit_my_application(
    app_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    success, errors, updated = await submit_application(app_id, current_user["_id"])
    if not success:
        if "not found" in " ".join(errors).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=errors[0])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Validation failed", "errors": errors},
        )
    # Notify user
    await create_notification(
        user_id=current_user["_id"],
        type="application_status_changed",
        title="Application submitted",
        message=(
            f"Your application {updated['case_id']} has been submitted successfully "
            "and is now awaiting review."
        ),
        link=f"/applications/{app_id}",
        send_email_if_enabled=True,
    )
    tname = await _type_name(updated["application_type_id"])
    return _to_detail(updated, type_name=tname)


@router.post("/applications/{app_id}/validate", response_model=ValidationResult)
async def validate_my_application(
    app_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    app = await get_application_by_id(app_id, user_id=current_user["_id"])
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    app_type = await db.application_types.find_one({"_id": app["application_type_id"]})
    if not app_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application type not found"
        )

    form_fields = app_type.get("form_fields", [])
    form_data = app.get("form_data", {})
    errors = validate_form_data(form_data, form_fields)
    score = calculate_validation_score(form_data, form_fields)

    # Identify which required fields are missing
    missing = [
        f["field_name"]
        for f in form_fields
        if f.get("is_required", False)
        and (
            form_data.get(f["field_name"]) is None
            or str(form_data[f["field_name"]]).strip() == ""
        )
    ]

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        validation_score=score,
        missing_fields=missing,
    )


@router.get("/applications/{app_id}/timeline", response_model=List[ApplicationTimelineEvent])
async def get_my_application_timeline(
    app_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    # Verify ownership (or admin)
    app = await get_application_by_id(app_id, user_id=current_user["_id"])
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    events = await get_application_timeline(app_id)
    return [
        ApplicationTimelineEvent(
            event_type=e["event_type"],
            details=e.get("details", {}),
            user_id=str(e["user_id"]) if e.get("user_id") else None,
            timestamp=e["timestamp"],
        )
        for e in events
    ]

@router.get("/admin/applications", response_model=ApplicationListResponse)
async def admin_list_applications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    user_id: Optional[str] = Query(None),
    type_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin),
):
    apps, total = await get_all_applications(
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        user_id_filter=user_id,
        type_id_filter=type_id,
    )
    items = [_to_list_item(a) for a in apps]
    return ApplicationListResponse(
        applications=items, total=total, page=page, page_size=page_size
    )


@router.get("/admin/applications/{app_id}", response_model=ApplicationDetail)
async def admin_get_application(
    app_id: str,
    current_user: dict = Depends(require_admin),
):
    app = await get_application_by_id(app_id)  # No user filter for admins
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    # Auto-advance to under_review if admin opens a submitted application
    if app["status"] == "submitted":
        success, _, app = await admin_change_status(
            app_id=app_id,
            new_status="under_review",
            admin_user_id=current_user["_id"],
        )
        if not success:
            app = await get_application_by_id(app_id)
        # Notify applicant
        if app:
            await create_notification(
                user_id=app["user_id"],
                type="application_status_changed",
                title="Application under review",
                message=f"Your application {app['case_id']} is now being reviewed by our team.",
                link=f"/applications/{app_id}",
                send_email_if_enabled=True,
            )
    tname = await _type_name(app["application_type_id"])
    return _to_detail(app, type_name=tname)


@router.patch("/admin/applications/{app_id}/status", response_model=ApplicationDetail)
async def admin_update_application_status(
    app_id: str,
    data: AdminStatusChangeRequest,
    current_user: dict = Depends(require_admin),
):

    success, err, updated = await admin_change_status(
        app_id=app_id,
        new_status=data.status,
        admin_user_id=current_user["_id"],
        notes=data.notes,
    )
    if not success:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in err.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=err)

    # Notify the applicant
    notification_map = {
        "approved": ("application_approved", "Application approved",
                     f"Congratulations! Your application {updated['case_id']} has been approved."),
        "rejected": ("application_rejected", "Application not approved",
                     f"Your application {updated['case_id']} was not approved. "
                     "Please review the admin notes for details."),
        "pending_info": ("information_requested", "Additional information requested",
                         f"Your application {updated['case_id']} requires additional information. "
                         "Please log in and update your application."),
        "under_review": ("application_status_changed", "Application under review",
                         f"Your application {updated['case_id']} is now under review."),
    }
    if data.status in notification_map:
        ntype, ntitle, nmsg = notification_map[data.status]
        await create_notification(
            user_id=updated["user_id"],
            type=ntype,
            title=ntitle,
            message=nmsg,
            link=f"/applications/{app_id}",
            send_email_if_enabled=True,
        )

    tname = await _type_name(updated["application_type_id"])
    return _to_detail(updated, type_name=tname)


@router.get("/admin/applications/{app_id}/timeline", response_model=List[ApplicationTimelineEvent])
async def admin_get_application_timeline(
    app_id: str,
    current_user: dict = Depends(require_admin),
):
    app = await get_application_by_id(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    events = await get_application_timeline(app_id)
    return [
        ApplicationTimelineEvent(
            event_type=e["event_type"],
            details=e.get("details", {}),
            user_id=str(e["user_id"]) if e.get("user_id") else None,
            timestamp=e["timestamp"],
        )
        for e in events
    ]
