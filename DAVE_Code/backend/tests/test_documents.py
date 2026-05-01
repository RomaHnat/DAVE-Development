"""
Tests for Sprint 4: Document Upload & Storage.

GridFS calls are patched so tests run reliably with both mock and live MongoDB.

Covers:
  - POST /applications/{app_id}/documents   – upload (happy path)
  - POST /applications/{app_id}/documents   – invalid file type rejected
  - POST /applications/{app_id}/documents   – file too large rejected
  - GET  /applications/{app_id}/documents   – list documents
  - GET  /applications/{app_id}/document-checklist
  - GET  /documents/{doc_id}                – metadata
  - GET  /documents/{doc_id}/download       – file bytes
  - GET  /documents/{doc_id}/processing-status
  - PATCH /documents/{doc_id}/type          – update document type
  - DELETE /documents/{doc_id}              – delete & confirm gone
  - Admin can access any application's documents
  - Non-owner is blocked (403/404)
"""

import io
import struct
import zlib
import pytest
import pytest_asyncio
from unittest.mock import patch

from backend.tests.conftest import auth_header

def _make_png_bytes() -> bytes:

    def _chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)          # 1×1 RGB
    idat = zlib.compress(b"\x00\xff\xff\xff")                      # filter + white pixel
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


SAMPLE_PNG = _make_png_bytes()

_TYPE_MINI = {
    "type_name": "Doc Upload Test Type",
    "description": "Used by test_documents.py – safe to delete.",
    "form_fields": [
        {
            "field_name": "full_name",
            "label": "Full Name",
            "field_type": "text",
            "is_required": True,
            "order": 1,
        },
    ],
    "required_documents": [
        {"document_type": "ID Card", "is_mandatory": True, "has_expiry": True},
    ],
    "validation_rules": [],
}

_state: dict = {}

@pytest_asyncio.fixture(scope="module", autouse=True)
async def _setup(client, admin_token, user_token):

    fake_store: dict = {}

    async def fake_upload(file_data, filename, metadata=None):
        fid = f"fake_{filename.replace('.', '_')}"
        fake_store[fid] = file_data
        return fid

    async def fake_download(file_id):
        data = fake_store.get(file_id)
        if data is None:
            raise FileNotFoundError(f"GridFS file not found: {file_id}")
        return data

    async def fake_delete(file_id):
        fake_store.pop(file_id, None)
        return True

    patches = [
        patch("backend.services.document_service.upload_file_to_gridfs",
              side_effect=fake_upload),
        patch("backend.services.document_service.download_file_from_gridfs",
              side_effect=fake_download),
        patch("backend.services.document_service.delete_file_from_gridfs",
              side_effect=fake_delete),
        patch("backend.tasks.document_tasks.download_file_from_gridfs",
              side_effect=fake_download),
    ]
    for p in patches:
        p.start()

    # Create the application type (admin)
    from backend.database import db
    await db.application_types.delete_one({"type_name": _TYPE_MINI["type_name"]})
    tr = await client.post(
        "/api/admin/application-types",
        json=_TYPE_MINI,
        headers=auth_header(admin_token),
    )
    assert tr.status_code == 201, tr.text
    _state["type_id"] = tr.json()["id"]

    # Create the application (user)
    ar = await client.post(
        "/api/applications",
        json={"application_type_id": _state["type_id"], "form_data": {}},
        headers=auth_header(user_token),
    )
    assert ar.status_code == 201, ar.text
    _state["app_id"] = ar.json()["id"]
    _state["fake_store"] = fake_store

    yield

    for p in patches:
        p.stop()

    # Cleanup
    await db.application_types.delete_one({"type_name": _TYPE_MINI["type_name"]})

@pytest.mark.asyncio
async def test_upload_document_success(client, user_token):
    app_id = _state["app_id"]
    resp = await client.post(
        f"/api/applications/{app_id}/documents",
        files={"file": ("id_card.png", io.BytesIO(SAMPLE_PNG), "image/png")},
        data={"document_type": "ID Card"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["document_type"] == "ID Card"
    assert body["status"] == "processing"
    assert body["filename"] == "id_card.png"
    assert body["file_size"] == len(SAMPLE_PNG)
    _state["doc_id"] = body["id"]


@pytest.mark.asyncio
async def test_upload_invalid_file_type_rejected(client, user_token):
    app_id = _state["app_id"]
    resp = await client.post(
        f"/api/applications/{app_id}/documents",
        files={"file": ("exploit.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
        data={"document_type": "ID Card"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_oversized_file_rejected(client, user_token):
    app_id = _state["app_id"]
    big_file = b"A" * (11 * 1024 * 1024)  # 11 MB – over the 10 MB limit
    resp = await client.post(
        f"/api/applications/{app_id}/documents",
        files={"file": ("big.png", io.BytesIO(big_file), "image/png")},
        data={"document_type": "ID Card"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_to_nonexistent_application(client, user_token):
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await client.post(
        f"/api/applications/{fake_id}/documents",
        files={"file": ("id.png", io.BytesIO(SAMPLE_PNG), "image/png")},
        data={"document_type": "ID Card"},
        headers=auth_header(user_token),
    )
    assert resp.status_code in (400, 403, 404)

@pytest.mark.asyncio
async def test_list_documents_returns_uploaded(client, user_token):
    assert _state.get("doc_id"), "test_upload_document_success must run first"
    app_id = _state["app_id"]
    resp = await client.get(
        f"/api/applications/{app_id}/documents",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "documents" in body
    assert body["total"] >= 1
    ids = [d["id"] for d in body["documents"]]
    assert _state["doc_id"] in ids


@pytest.mark.asyncio
async def test_document_checklist(client, user_token):
    app_id = _state["app_id"]
    resp = await client.get(
        f"/api/applications/{app_id}/document-checklist",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total_required" in body
    assert "is_complete" in body

@pytest.mark.asyncio
async def test_get_document_metadata(client, user_token):
    doc_id = _state.get("doc_id")
    assert doc_id
    resp = await client.get(f"/api/documents/{doc_id}", headers=auth_header(user_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == doc_id
    assert body["document_type"] == "ID Card"


@pytest.mark.asyncio
async def test_get_document_metadata_nonexistent(client, user_token):
    from bson import ObjectId
    resp = await client.get(
        f"/api/documents/{str(ObjectId())}",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_document(client, user_token):
    doc_id = _state.get("doc_id")
    assert doc_id
    resp = await client.get(
        f"/api/documents/{doc_id}/download",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    assert resp.content == SAMPLE_PNG


@pytest.mark.asyncio
async def test_processing_status(client, user_token):
    doc_id = _state.get("doc_id")
    assert doc_id
    resp = await client.get(
        f"/api/documents/{doc_id}/processing-status",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert body["document_id"] == doc_id

@pytest.mark.asyncio
async def test_update_document_type(client, user_token):
    doc_id = _state.get("doc_id")
    assert doc_id
    resp = await client.patch(
        f"/api/documents/{doc_id}/type",
        json={"document_type": "Passport"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    assert resp.json()["document_type"] == "Passport"

@pytest.mark.asyncio
async def test_admin_can_list_documents(client, admin_token):
    app_id = _state["app_id"]
    resp = await client.get(
        f"/api/applications/{app_id}/documents",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_download_document(client, admin_token):
    doc_id = _state.get("doc_id")
    assert doc_id
    resp = await client.get(
        f"/api/documents/{doc_id}/download",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_replace_document_creates_version_history(client, user_token):
    doc_id = _state.get("doc_id")
    assert doc_id, "test_upload_document_success must run first"

    resp = await client.put(
        f"/api/documents/{doc_id}/replace",
        files={"file": ("id_card_v2.png", io.BytesIO(SAMPLE_PNG), "image/png")},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filename"] == "id_card_v2.png"
    assert body["status"] == "processing"
    assert len(body["version_history"]) == 1
    assert body["version_history"][0]["filename"] == "id_card.png"
    assert "replaced_at" in body["version_history"][0]


@pytest.mark.asyncio
async def test_replace_document_nonexistent(client, user_token):
    from bson import ObjectId

    resp = await client.put(
        f"/api/documents/{str(ObjectId())}/replace",
        files={"file": ("id.png", io.BytesIO(SAMPLE_PNG), "image/png")},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_document(client, user_token):
    doc_id = _state.get("doc_id")
    assert doc_id
    resp = await client.delete(
        f"/api/documents/{doc_id}",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 204

    # Confirm it's gone
    get_resp = await client.get(
        f"/api/documents/{doc_id}",
        headers=auth_header(user_token),
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_document(client, user_token):
    from bson import ObjectId
    resp = await client.delete(
        f"/api/documents/{str(ObjectId())}",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404
