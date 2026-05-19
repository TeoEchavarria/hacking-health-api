"""
Caregiver-only read endpoints.

All endpoints under /caregiver/* are:
  * GET-only (caregivers can never mutate patient data)
  * Authenticated via JWT (verify_token_jwt → user_id)
  * Authorized via require_caregiver_access for any patient-scoped path:
      - 404 if patient_id is unknown
      - 403 if requester is the patient themselves (caregiver-only path)
      - 403 if no active pairing exists

The actual data fetching delegates to existing services (HealthService,
PairingService) — this module is a thin authorization + projection layer.
"""

from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from bson.objectid import ObjectId
from bson.errors import InvalidId

from src._config.logger import get_logger
from src.core.database import get_database
from src.core.authorization import require_caregiver_access
from src.domains.auth.routes import verify_token_jwt
from src.domains.health.services import HealthService
from src.domains.pairing.services import PairingService

logger = get_logger(__name__)

router = APIRouter(prefix="/caregiver", tags=["caregiver"])


# =============================================================================
# GET /caregiver/patients
# =============================================================================

@router.get("/patients")
async def list_my_patients(
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database),
) -> Dict[str, Any]:
    """
    List patients actively paired with the authenticated caregiver.

    Returns only display-safe fields: patient_id, name, profile_picture,
    pairing_id, activated_at. Never returns email, password, or tokens.
    """
    pairing_service = PairingService(db)
    pairings = await pairing_service.get_user_pairings(user_id, role="caregiver")

    patients: List[Dict[str, Any]] = []
    for p in pairings:
        patient_id = p.get("patientId")
        # Best-effort enrich with profile_picture (not stored on pairing doc)
        profile_picture = None
        if patient_id:
            try:
                patient_doc = await db.users.find_one(
                    {"_id": ObjectId(patient_id)},
                    {"profile_picture": 1, "name": 1},
                )
                if patient_doc:
                    profile_picture = patient_doc.get("profile_picture")
            except (InvalidId, TypeError):
                pass

        patients.append({
            "patient_id": patient_id,
            "name": p.get("patientName"),
            "profile_picture": profile_picture,
            "pairing_id": str(p.get("_id")) if p.get("_id") else None,
            "activated_at": p.get("activatedAt"),
        })

    return {"patients": patients, "count": len(patients)}


# =============================================================================
# GET /caregiver/patients/{patient_id}/history/bp
# =============================================================================

@router.get("/patients/{patient_id}/history/bp")
async def get_patient_bp_history(
    patient_id: str,
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database),
) -> Dict[str, Any]:
    """Blood pressure raw readings for a paired patient."""
    patient = await require_caregiver_access(patient_id, user_id, db)

    # Translate date_from/date_to to a `days` window for the existing BP service.
    if date_from and date_to:
        days = max(1, min(180, (date_to - date_from).days + 1))
    elif date_from:
        days = max(1, min(180, (date.today() - date_from).days + 1))
    else:
        days = 30

    service = HealthService(db)
    bp_result = await service.get_patient_blood_pressure_readings(
        patient_id=patient_id, days=days, limit=limit
    )

    # `bp_result` is a dict {patient_id, patient_name, days_requested,
    # readings: [...], count}. The caregiver endpoint only exposes the
    # actual readings list plus the safe patient projection.
    readings_list = bp_result.get("readings", []) if isinstance(bp_result, dict) else []

    return {
        "patient": patient,
        "readings": readings_list,
        "count": len(readings_list),
    }


# =============================================================================
# GET /caregiver/patients/{patient_id}/history/steps
# =============================================================================

@router.get("/patients/{patient_id}/history/steps")
async def get_patient_steps_history(
    patient_id: str,
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database),
) -> Dict[str, Any]:
    """Daily steps history for a paired patient."""
    patient = await require_caregiver_access(patient_id, user_id, db)

    service = HealthService(db)
    history = await service.get_steps_history(
        patient_id=patient_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )

    return {"patient": patient, **history}


# =============================================================================
# GET /caregiver/patients/{patient_id}/history/sleep
# =============================================================================

@router.get("/patients/{patient_id}/history/sleep")
async def get_patient_sleep_history(
    patient_id: str,
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database),
) -> Dict[str, Any]:
    """Daily sleep history for a paired patient (value in minutes)."""
    patient = await require_caregiver_access(patient_id, user_id, db)

    service = HealthService(db)
    history = await service.get_sleep_history(
        patient_id=patient_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )

    return {"patient": patient, **history}


# =============================================================================
# GET /caregiver/patients/{patient_id}/history/summary
# =============================================================================

@router.get("/patients/{patient_id}/history/summary")
async def get_patient_summary(
    patient_id: str,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database),
) -> Dict[str, Any]:
    """
    30-day rolling aggregated summary for a paired patient:
      - Average BP (systolic/diastolic) + reading count
      - Total steps + daily average
      - Average sleep (minutes/hours)
    """
    patient = await require_caregiver_access(patient_id, user_id, db)

    service = HealthService(db)
    summary = await service.get_30day_summary(patient_id)

    return {"patient": patient, **summary}
