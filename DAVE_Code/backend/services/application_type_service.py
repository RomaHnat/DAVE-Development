from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from backend.database import db

def _validate_unique_field_names(form_fields: List[Dict]) -> Optional[str]:
    seen: set[str] = set()
    for field in form_fields:
        name = field.get("field_name", "")
        if name in seen:
            return f"Duplicate field_name '{name}' in form_fields"
        seen.add(name)
    return None


def _validate_unique_document_types(required_docs: List[Dict]) -> Optional[str]:
    seen: set[str] = set()
    for doc in required_docs:
        dtype = doc.get("document_type", "")
        if dtype in seen:
            return f"Duplicate document_type '{dtype}' in required_documents"
        seen.add(dtype)
    return None


def _validate_conditional_fields(
    form_fields: List[Dict], required_docs: List[Dict]
) -> Optional[str]:
    field_names = {f.get("field_name") for f in form_fields}

    for field in form_fields:
        cond = field.get("conditional_display")
        if cond and cond.get("field") not in field_names:
            return (
                f"conditional_display on '{field.get('field_name')}' references "
                f"unknown field '{cond.get('field')}'"
            )

    for doc in required_docs:
        cond = doc.get("conditional_requirement")
        if cond and cond.get("field") not in field_names:
            return (
                f"conditional_requirement on document '{doc.get('document_type')}' "
                f"references unknown field '{cond.get('field')}'"
            )
    return None


def validate_application_type_config(
    form_fields: List[Dict], required_docs: List[Dict]
) -> Optional[str]:
    err = _validate_unique_field_names(form_fields)
    if err:
        return err
    err = _validate_unique_document_types(required_docs)
    if err:
        return err
    err = _validate_conditional_fields(form_fields, required_docs)
    return err

async def create_application_type(data: Dict[str, Any], created_by: ObjectId) -> dict:
    now = datetime.now(timezone.utc)
    doc = {
        "type_name": data["type_name"],
        "description": data["description"],
        "form_fields": [f if isinstance(f, dict) else f.model_dump() for f in data.get("form_fields", [])],
        "required_documents": [d if isinstance(d, dict) else d.model_dump() for d in data.get("required_documents", [])],
        "validation_rules": [r if isinstance(r, dict) else r.model_dump() for r in data.get("validation_rules", [])],
        "status": "active",
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.application_types.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_application_type(type_id: str) -> Optional[dict]:
    if not ObjectId.is_valid(type_id):
        return None
    return await db.application_types.find_one({"_id": ObjectId(type_id)})


async def get_all_application_types(include_inactive: bool = False) -> List[dict]:
    query: Dict = {} if include_inactive else {"status": "active"}
    cursor = db.application_types.find(query).sort("type_name", 1)
    return await cursor.to_list(length=None)


async def update_application_type(
    type_id: str, data: Dict[str, Any]
) -> Optional[dict]:
    if not ObjectId.is_valid(type_id):
        return None
    update_data: Dict[str, Any] = {}
    for key in ("type_name", "description", "form_fields", "required_documents", "validation_rules"):
        if key in data and data[key] is not None:
            val = data[key]
            # Serialise Pydantic sub-models if necessary
            if isinstance(val, list):
                val = [item if isinstance(item, dict) else item.model_dump() for item in val]
            update_data[key] = val
    update_data["updated_at"] = datetime.now(timezone.utc)
    await db.application_types.update_one(
        {"_id": ObjectId(type_id)},
        {"$set": update_data},
    )
    return await db.application_types.find_one({"_id": ObjectId(type_id)})


async def soft_delete_application_type(type_id: str) -> bool:
    if not ObjectId.is_valid(type_id):
        return False
    result = await db.application_types.update_one(
        {"_id": ObjectId(type_id)},
        {"$set": {"status": "inactive", "updated_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count > 0
