from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
import io

from backend.auth.dependencies import get_current_active_user
from backend.auth.permissions import require_admin
from backend.schemas.document import (
    DocumentChecklist,
    DocumentListResponse,
    DocumentResponse,
    DocumentTypeUpdate,
)
from backend.services.document_service import (
    delete_document,
    get_application_documents,
    get_document_by_id,
    get_document_checklist,
    replace_document,
    update_document_type,
    upload_document,
    download_document,
)
from backend.tasks.document_tasks import process_document

router = APIRouter(tags=["Documents"])

@router.post(
    "/applications/{app_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_to_application(
    app_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    current_user: dict = Depends(get_current_active_user),
):

    file_data = await file.read()
    mime_type = file.content_type or "application/octet-stream"

    try:
        doc = await upload_document(
            application_id=app_id,
            user_id=str(current_user["_id"]),
            filename=file.filename or "upload",
            file_data=file_data,
            document_type=document_type,
            mime_type=mime_type,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Trigger background OCR processing
    background_tasks.add_task(
        process_document,
        document_id=doc["id"],
        gridfs_file_id=doc["gridfs_file_id"],
        document_type=document_type,
    )

    return DocumentResponse(**doc)

@router.get("/applications/{app_id}/documents", response_model=DocumentListResponse)
async def list_application_documents(
    app_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    role = current_user.get("role", "applicant")
    try:
        docs = await get_application_documents(
            application_id=app_id,
            user_id=str(current_user["_id"]),
            role=role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return DocumentListResponse(
        documents=[DocumentResponse(**d) for d in docs],
        total=len(docs),
    )

@router.get("/applications/{app_id}/document-checklist", response_model=DocumentChecklist)
async def document_checklist(
    app_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    role = current_user.get("role", "applicant")
    try:
        checklist = await get_document_checklist(
            application_id=app_id,
            user_id=str(current_user["_id"]),
            role=role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return DocumentChecklist(**checklist)

@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    role = current_user.get("role", "applicant")
    try:
        doc = await get_document_by_id(doc_id, str(current_user["_id"]), role)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return DocumentResponse(**doc)

@router.get("/documents/{doc_id}/download")
async def download_document_file(
    doc_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    role = current_user.get("role", "applicant")
    try:
        file_data, filename, mime_type = await download_document(
            doc_id, str(current_user["_id"]), role
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return Response(
        content=file_data,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/documents/{doc_id}/preview")
async def preview_document(
    doc_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    role = current_user.get("role", "applicant")
    try:
        file_data, filename, mime_type = await download_document(
            doc_id, str(current_user["_id"]), role
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    try:
        from backend.services.preview_service import (
            generate_image_thumbnail,
            generate_pdf_thumbnail,
        )

        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            thumbnail = generate_pdf_thumbnail(file_data)
        else:
            thumbnail = generate_image_thumbnail(file_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not generate preview: {exc}",
        )

    return Response(content=thumbnail, media_type="image/png")

@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_endpoint(
    doc_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    role = current_user.get("role", "applicant")
    try:
        await delete_document(doc_id, str(current_user["_id"]), role)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@router.patch("/documents/{doc_id}/type", response_model=DocumentResponse)
async def update_type(
    doc_id: str,
    body: DocumentTypeUpdate,
    current_user: dict = Depends(get_current_active_user),
):
    try:
        doc = await update_document_type(doc_id, str(current_user["_id"]), body.document_type)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return DocumentResponse(**doc)

@router.get("/documents/{doc_id}/processing-status")
async def processing_status(
    doc_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    role = current_user.get("role", "applicant")
    try:
        doc = await get_document_by_id(doc_id, str(current_user["_id"]), role)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return {
        "document_id": doc_id,
        "status": doc["status"],
        "processed_at": doc.get("processed_at"),
        "ocr_metadata": doc.get("ocr_metadata", {}),
    }


@router.put("/documents/{doc_id}/replace", response_model=DocumentResponse)
async def replace_document_file(
    doc_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
):
    file_data = await file.read()
    mime_type = file.content_type or "application/octet-stream"

    try:
        doc = await replace_document(
            document_id=doc_id,
            user_id=str(current_user["_id"]),
            filename=file.filename or "upload",
            file_data=file_data,
            mime_type=mime_type,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    background_tasks.add_task(
        process_document,
        document_id=doc["id"],
        gridfs_file_id=doc["gridfs_file_id"],
        document_type=doc["document_type"],
    )

    return DocumentResponse(**doc)

@router.get("/applications/{app_id}/ai-document-suggestions")
async def ai_document_suggestions(
    app_id: str,
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:

    from bson import ObjectId
    from backend.database import db
    from backend.services.openai_service import suggest_required_documents

    role = current_user.get("role", "applicant")
    try:
        app_oid = ObjectId(app_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid application ID")

    if role in ("admin", "super_admin"):
        app = await db.applications.find_one({"_id": app_oid})
    else:
        app = await db.applications.find_one({"_id": app_oid, "user_id": current_user["_id"]})

    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    app_type = await db.application_types.find_one({"_id": app.get("application_type_id")})
    app_type_name: str = (app_type or {}).get("name", "Unknown Application Type")

    # Collect existing required document types so GPT doesn't repeat them
    existing_required: List[str] = [
        req.get("document_type", "")
        for req in (app_type or {}).get("required_documents", [])
        if req.get("document_type")
    ]

    suggestions = await suggest_required_documents(
        application_type_name=app_type_name,
        form_data=app.get("form_data") or {},
        already_required=existing_required,
    )

    return {
        "application_id": app_id,
        "suggestions": suggestions,
        "ai_powered": len(suggestions) > 0,
    }

@router.post("/documents/{doc_id}/validate", response_model=Dict[str, Any])
async def validate_document(
    doc_id: str,
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:

    from backend.services.document_validation_service import validate_document_against_application

    role = current_user.get("role", "applicant")
    try:
        doc = await get_document_by_id(doc_id, str(current_user["_id"]), role)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    if doc.get("status") not in ("processed",):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be in 'processed' status before validation.",
        )

    result = await validate_document_against_application(doc_id)
    return {"document_id": doc_id, "validation_result": result}
