from datetime import datetime, timezone
from typing import Optional, Dict, Any
from bson import ObjectId
from fastapi import Request

from backend.database import db

async def log_user_action(
    user_id: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None
) -> str:
    ip_address = None
    user_agent = None
    
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
    
    audit_log = {
        "user_id": ObjectId(user_id) if user_id else None,
        "action": action,
        "entity_type": entity_type,
        "entity_id": ObjectId(entity_id) if entity_id and len(entity_id) == 24 else entity_id,
        "details": details or {},
        "ip_address": ip_address,
        "user_agent": user_agent,
        "timestamp": datetime.now(timezone.utc)
    }
    
    result = await db.audit_logs.insert_one(audit_log)
    return str(result.inserted_id)

async def get_user_activity(
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    action: Optional[str] = None
) -> tuple[list, int]:

    query = {"user_id": ObjectId(user_id)}
    
    if action:
        query["action"] = action
    
    # Get total count
    total = await db.audit_logs.count_documents(query)
    
    # Get paginated results
    skip = (page - 1) * page_size
    cursor = db.audit_logs.find(query).sort("timestamp", -1).skip(skip).limit(page_size)
    logs = await cursor.to_list(length=page_size)
    
    return logs, total

async def get_system_activity(
    page: int = 1,
    page_size: int = 50,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None
) -> tuple[list, int]:

    query = {}
    
    if user_id:
        query["user_id"] = ObjectId(user_id)
    if action:
        query["action"] = action
    if entity_type:
        query["entity_type"] = entity_type
    
    # Get total count
    total = await db.audit_logs.count_documents(query)
    
    # Get paginated results with user email lookup
    skip = (page - 1) * page_size
    
    pipeline = [
        {"$match": query},
        {"$sort": {"timestamp": -1}},
        {"$skip": skip},
        {"$limit": page_size},
        {
            "$lookup": {
                "from": "users",
                "localField": "user_id",
                "foreignField": "_id",
                "as": "user_info"
            }
        },
        {
            "$addFields": {
                "user_email": {
                    "$arrayElemAt": ["$user_info.email", 0]
                }
            }
        },
        {
            "$project": {
                "user_info": 0
            }
        }
    ]
    
    logs = await db.audit_logs.aggregate(pipeline).to_list(length=page_size)
    
    return logs, total
