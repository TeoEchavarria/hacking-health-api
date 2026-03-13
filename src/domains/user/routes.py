from fastapi import APIRouter, Depends, HTTPException
from src.core.database import get_database
from src.domains.auth.routes import verify_token
from src.domains.user.schemas import UserResponse, OAuthProviderInfo
from bson.objectid import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import List

user_router = APIRouter(prefix="/user", tags=["user"])
users_router = APIRouter(prefix="/users", tags=["user"])


def _user_doc_to_response(doc: dict) -> UserResponse:
    if not doc:
        return None
    created = doc.get("created_at")
    updated = doc.get("updated_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    elif not created:
        created = datetime.now(timezone.utc).isoformat()
    if isinstance(updated, datetime):
        updated = updated.isoformat()
    elif not updated:
        updated = datetime.now(timezone.utc).isoformat()
    
    # Process OAuth providers
    oauth_providers = []
    for provider in doc.get("oauth_providers", []):
        linked_at = provider.get("linked_at")
        if isinstance(linked_at, datetime):
            linked_at = linked_at.isoformat()
        elif not linked_at:
            linked_at = created
        
        oauth_providers.append(OAuthProviderInfo(
            provider=provider.get("provider", ""),
            provider_email=provider.get("provider_email", ""),
            linked_at=linked_at
        ))
    
    return UserResponse(
        id=str(doc["_id"]),
        username=doc.get("username", ""),
        email=doc.get("email"),
        email_verified=doc.get("email_verified", False),
        name=doc.get("name"),
        profile_picture=doc.get("profile_picture"),
        oauth_providers=oauth_providers,
        created_at=created,
        updated_at=updated,
    )


@user_router.get("/profile", response_model=UserResponse)
async def get_current_user(
    user_id: str = Depends(verify_token),
    db=Depends(get_database),
):
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_doc_to_response(user)


@user_router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: str,
    _: str = Depends(verify_token),
    db=Depends(get_database),
):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_doc_to_response(user)


class BatchUserIds(BaseModel):
    user_ids: List[str]


@users_router.post("/batch")
async def get_users_batch(
    body: BatchUserIds,
    _: str = Depends(verify_token),
    db=Depends(get_database),
):
    ids = []
    for uid in body.user_ids:
        try:
            ids.append(ObjectId(uid))
        except Exception:
            continue
    cursor = db.users.find({"_id": {"$in": ids}})
    users = []
    async for doc in cursor:
        users.append(_user_doc_to_response(doc))
    return {"users": users}
