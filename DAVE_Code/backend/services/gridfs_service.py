from __future__ import annotations

import io
from typing import Any, Dict, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from backend.database import get_motor_db


async def _bucket() -> AsyncIOMotorGridFSBucket:
    motor_db = await get_motor_db()
    return AsyncIOMotorGridFSBucket(motor_db, bucket_name="documents")


async def upload_file_to_gridfs(
    file_data: bytes,
    filename: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:

    bucket = await _bucket()
    file_id = await bucket.upload_from_stream(
        filename,
        io.BytesIO(file_data),
        metadata=metadata or {},
    )
    return str(file_id)


async def download_file_from_gridfs(file_id: str) -> bytes:

    bucket = await _bucket()
    buf = io.BytesIO()
    try:
        await bucket.download_to_stream(ObjectId(file_id), buf)
    except Exception as exc:
        raise FileNotFoundError(f"GridFS file {file_id} not found") from exc
    return buf.getvalue()


async def delete_file_from_gridfs(file_id: str) -> bool:
    bucket = await _bucket()
    try:
        await bucket.delete(ObjectId(file_id))
        return True
    except Exception:
        return False


async def get_file_metadata(file_id: str) -> Optional[Dict[str, Any]]:
    bucket = await _bucket()
    cursor = bucket.find({"_id": ObjectId(file_id)})
    async for doc in cursor:
        return {
            "file_id": str(doc["_id"]),
            "filename": doc.get("filename"),
            "length": doc.get("length"),
            "chunk_size": doc.get("chunkSize"),
            "upload_date": doc.get("uploadDate"),
            "metadata": doc.get("metadata", {}),
        }
    return None
