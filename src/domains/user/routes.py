from fastapi import APIRouter, Depends, HTTPException
from src.core.database import get_database
from src.domains.auth.routes import verify_token
from src.domains.user.schemas import UserResponse, OAuthProviderInfo, FullUserProfileResponse, ConnectionInfo
from src.domains.pairing.services import PairingService
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


@user_router.get("/profile/full", response_model=FullUserProfileResponse)
async def get_full_user_profile(
    user_id: str = Depends(verify_token),
    db=Depends(get_database),
):
    """
    Get full user profile with inferred role and connections.
    
    Role is inferred from active pairings:
    - If user has active pairings as caregiver -> role = "caregiver"
    - If user has active pairings as patient -> role = "patient"
    - If both -> role = "caregiver" (prioritize caregiver role)
    - If neither -> role = "none"
    """
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    pairing_service = PairingService(db)
    
    # Get pairings where user is caregiver
    caregiver_pairings = await pairing_service.get_user_pairings(user_id, role="caregiver")
    
    # Get pairings where user is patient
    patient_pairings = await pairing_service.get_user_pairings(user_id, role="patient")
    
    # Determine role
    if caregiver_pairings:
        role = "caregiver"
    elif patient_pairings:
        role = "patient"
    else:
        role = "none"
    
    # Build connections list
    connections = []
    
    # Add patients that this user cares for
    for pairing in caregiver_pairings:
        # Get patient's profile picture
        patient_user = await db.users.find_one({"_id": ObjectId(pairing["patientId"])})
        connections.append(ConnectionInfo(
            user_id=pairing["patientId"],
            name=pairing.get("patientName", "Usuario"),
            role="patient",  # This person is a patient to the current user
            profile_picture=patient_user.get("profile_picture") if patient_user else None
        ))
    
    # Add caregivers that care for this user
    for pairing in patient_pairings:
        # Get caregiver's profile picture
        caregiver_user = await db.users.find_one({"_id": ObjectId(pairing["caregiverId"])})
        connections.append(ConnectionInfo(
            user_id=pairing["caregiverId"],
            name=pairing.get("caregiverName", "Cuidador"),
            role="caregiver",  # This person is a caregiver to the current user
            profile_picture=caregiver_user.get("profile_picture") if caregiver_user else None
        ))
    
    # Format timestamps
    created = user.get("created_at")
    updated = user.get("updated_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    elif not created:
        created = datetime.now(timezone.utc).isoformat()
    if isinstance(updated, datetime):
        updated = updated.isoformat()
    elif not updated:
        updated = datetime.now(timezone.utc).isoformat()
    
    return FullUserProfileResponse(
        id=str(user["_id"]),
        name=user.get("name"),
        email=user.get("email"),
        profile_picture=user.get("profile_picture"),
        role=role,
        connections=connections,
        created_at=created,
        updated_at=updated
    )


class FcmTokenUpdate(BaseModel):
    fcm_token: str


@user_router.patch("/fcm-token")
async def update_fcm_token(
    body: FcmTokenUpdate,
    user_id: str = Depends(verify_token),
    db=Depends(get_database),
):
    """
    Update user's FCM token for push notifications.
    
    Called by the mobile app when:
    - App is installed for the first time
    - FCM token is rotated/refreshed
    """
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "fcmToken": body.fcm_token,
                "fcmTokenUpdatedAt": datetime.now(timezone.utc)
            }
        }
    )
    return {"success": True}


# Collections whose documents are OWNED by a single user, keyed by "userId".
_USER_OWNED_COLLECTIONS = [
    "blood_pressure_readings",
    "medications",
    "medication_takes",
    "health_metrics",
    "sensor_batches",
    "locations",
]

# Collections that may reference a user under several id fields.
_USER_MULTIFIELD_COLLECTIONS = {
    "notifications": ["userId", "patientId", "caregiverId"],
    "sync_requests": ["userId", "patientId", "caregiverId"],
    "alerts": ["userId", "patientId", "caregiverId"],
}


async def delete_user_and_data(db, user_id: str) -> dict:
    """
    Hard-delete a user and ALL of their data across collections (account + data
    erasure). Idempotent and scoped to a single user.

    - Health data owned by the user (keyed by ``userId``) is deleted.
    - Pairings where the user is patient OR caregiver are deleted (ending the
      relationship for the other party too — their app reconciles on next sync).
    - The user's OWN biometric events (as patient) are deleted; for events where
      they were a caregiver of SOMEONE ELSE they are merely unlinked (pulled from
      ``caregiverIds``/``readByCaregivers``) so that patient keeps their data.
    - Finally the user document itself is removed (this also drops the embedded
      refresh-token tracking and ``fcmToken``).

    Returns a per-collection summary of how many docs were affected.
    """
    summary: dict = {}

    for coll in _USER_OWNED_COLLECTIONS:
        res = await db[coll].delete_many({"userId": user_id})
        summary[coll] = res.deleted_count

    for coll, fields in _USER_MULTIFIELD_COLLECTIONS.items():
        res = await db[coll].delete_many({"$or": [{f: user_id} for f in fields]})
        summary[coll] = res.deleted_count

    pairings_res = await db.pairings.delete_many(
        {"$or": [{"patientId": user_id}, {"caregiverId": user_id}]}
    )
    summary["pairings"] = pairings_res.deleted_count

    # Biometric events the user owns as the patient.
    own_events = await db.biometric_events.delete_many({"patientId": user_id})
    summary["biometric_events_owned"] = own_events.deleted_count
    # Events of OTHER patients where this user was a caregiver: just unlink them.
    unlinked = await db.biometric_events.update_many(
        {"$or": [{"caregiverIds": user_id}, {"caregiverId": user_id}]},
        {"$pull": {"caregiverIds": user_id, "readByCaregivers": user_id}},
    )
    summary["biometric_events_unlinked"] = unlinked.modified_count
    await db.biometric_events.update_many(
        {"caregiverId": user_id}, {"$set": {"caregiverId": None}}
    )

    # The user document itself.
    try:
        user_res = await db.users.delete_one({"_id": ObjectId(user_id)})
        summary["users"] = user_res.deleted_count
    except Exception:
        summary["users"] = 0

    return summary


@user_router.delete("/account")
async def delete_account(
    user_id: str = Depends(verify_token),
    db=Depends(get_database),
):
    """
    Permanently delete the authenticated user's account and ALL their data.

    Scoped to the caller (``user_id`` comes from the token), so a user can only
    ever delete their own account. This is irreversible.
    """
    summary = await delete_user_and_data(db, user_id)
    return {"success": True, "deleted": summary}


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
