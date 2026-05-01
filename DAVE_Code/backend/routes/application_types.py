from typing import List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth.dependencies import get_current_active_user
from backend.auth.permissions import require_admin
from backend.database import db
from backend.schemas.application_type import (
    ApplicationTypeCreate,
    ApplicationTypeResponse,
    ApplicationTypeSummaryResponse,
    ApplicationTypeUpdate,
)
from backend.services.application_type_service import (
    create_application_type,
    get_all_application_types,
    get_application_type,
    soft_delete_application_type,
    update_application_type,
    validate_application_type_config,
)

router = APIRouter(tags=["Application Types"])

def _to_response(doc: dict) -> ApplicationTypeResponse:
    return ApplicationTypeResponse(
        id=str(doc["_id"]),
        type_name=doc["type_name"],
        description=doc["description"],
        form_fields=doc.get("form_fields", []),
        required_documents=doc.get("required_documents", []),
        validation_rules=doc.get("validation_rules", []),
        status=doc["status"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )

@router.get("/application-types", response_model=List[ApplicationTypeSummaryResponse])
async def list_application_types():
    types = await get_all_application_types()
    return [
        ApplicationTypeSummaryResponse(
            id=str(t["_id"]),
            type_name=t["type_name"],
            description=t["description"],
            required_docs_count=len(t.get("required_documents", [])),
            form_fields_count=len(t.get("form_fields", [])),
            status=t["status"],
        )
        for t in types
    ]

@router.get("/application-types/{type_id}", response_model=ApplicationTypeResponse)
async def get_application_type_detail(type_id: str):
    app_type = await get_application_type(type_id)
    if not app_type or app_type.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application type not found",
        )
    return _to_response(app_type)

@router.post(
    "/admin/application-types",
    response_model=ApplicationTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_new_application_type(
    data: ApplicationTypeCreate,
    current_user: dict = Depends(require_admin),
):
    # Check name uniqueness among active types
    existing = await db.application_types.find_one(
        {"type_name": data.type_name, "status": "active"}
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An active application type named '{data.type_name}' already exists",
        )

    # Validate configuration logic
    form_fields_dicts = [f.model_dump() for f in data.form_fields]
    req_docs_dicts = [d.model_dump() for d in data.required_documents]
    err = validate_application_type_config(form_fields_dicts, req_docs_dicts)
    if err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)

    created = await create_application_type(data.model_dump(), current_user["_id"])
    return _to_response(created)


@router.put(
    "/admin/application-types/{type_id}",
    response_model=ApplicationTypeResponse,
)
async def update_existing_application_type(
    type_id: str,
    data: ApplicationTypeUpdate,
    current_user: dict = Depends(require_admin),
):
    app_type = await get_application_type(type_id)
    if not app_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application type not found",
        )

    update_dict = data.model_dump(exclude_none=True)

    # If field names are changing, validate uniqueness of new ones
    new_fields = [f.model_dump() for f in data.form_fields] if data.form_fields else app_type.get("form_fields", [])
    new_docs = [d.model_dump() for d in data.required_documents] if data.required_documents else app_type.get("required_documents", [])
    err = validate_application_type_config(new_fields, new_docs)
    if err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)

    updated = await update_application_type(type_id, update_dict)
    return _to_response(updated)


@router.delete("/admin/application-types/{type_id}", response_model=dict)
async def delete_application_type(
    type_id: str,
    current_user: dict = Depends(require_admin),
):
    app_type = await get_application_type(type_id)
    if not app_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application type not found",
        )

    # Prevent deletion if active applications depend on this type
    active_count = await db.applications.count_documents(
        {
            "application_type_id": ObjectId(type_id),
            "status": {"$in": ["pending", "submitted", "under_review"]},
        }
    )
    if active_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot deactivate: {active_count} application(s) are currently "
                "in progress with this type"
            ),
        )

    await soft_delete_application_type(type_id)
    return {"message": f"Application type '{app_type['type_name']}' deactivated"}


@router.get(
    "/admin/application-types",
    response_model=List[ApplicationTypeResponse],
)
async def admin_list_all_application_types(
    current_user: dict = Depends(require_admin),
):
    types = await get_all_application_types(include_inactive=True)
    return [_to_response(t) for t in types]
