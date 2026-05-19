"""
Authorization service for patient data access control.

Centralizes authorization logic to avoid duplication across domains.
Follows Single Responsibility Principle and DRY (Don't Repeat Yourself).
"""

import logging
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Header, status
from bson.objectid import ObjectId
from bson.errors import InvalidId

from src.core.repositories.pairing_repository import IPairingRepository
from src.core.exceptions import PatientAccessDeniedException
from src.core.database import get_database


logger = logging.getLogger(__name__)


class AuthorizationService:
    """
    Authorization service for verifying patient data access.
    
    Implements access control logic: users can access their own data,
    or caregiver's can access data of patients they're paired with.
    """
    
    def __init__(self, pairing_repo: IPairingRepository):
        """
        Initialize authorization service.
        
        Args:
            pairing_repo: Pairing repository for checking relationships
        """
        self.pairing_repo = pairing_repo
    
    async def verify_patient_access(
        self, 
        requester_id: str, 
        patient_id: str
    ) -> bool:
        """
        Verify if requester has access to patient's data.
        
        Access is granted if:
        1. requester_id == patient_id (accessing own data)
        2. requester is an active caregiver for this patient
        
        Args:
            requester_id: ID of the user making the request
            patient_id: ID of the patient whose data is being accessed
            
        Returns:
            True if access is allowed, False otherwise
        """
        # Delegate to repository's verify_access method
        has_access = await self.pairing_repo.verify_access(requester_id, patient_id)
        
        if has_access:
            if requester_id == patient_id:
                logger.debug(f"User {requester_id} accessing own data")
            else:
                logger.debug(
                    f"Caregiver {requester_id} has active pairing with patient {patient_id}"
                )
        else:
            logger.warning(
                f"Access denied: User {requester_id} attempted to access "
                f"data of patient {patient_id} without valid pairing"
            )
        
        return has_access
    
    async def require_patient_access(
        self, 
        requester_id: str, 
        patient_id: str
    ) -> None:
        """
        Require patient access or raise exception.
        
        Args:
            requester_id: ID of the user making the request
            patient_id: ID of the patient whose data is being accessed
            
        Raises:
            PatientAccessDeniedException: If access is not allowed
        """
        has_access = await self.verify_patient_access(requester_id, patient_id)
        
        if not has_access:
            raise PatientAccessDeniedException(requester_id, patient_id)


# === FastAPI Dependency Functions ===

def get_authorization_service(
    pairing_repo: IPairingRepository
) -> AuthorizationService:
    """
    FastAPI dependency to get AuthorizationService instance.
    
    Args:
        pairing_repo: Injected pairing repository
        
    Returns:
        AuthorizationService instance
    """
    return AuthorizationService(pairing_repo)


async def require_patient_access_dependency(
    patient_id: str,
    requester_id: str,
    authorization_service: AuthorizationService = Depends(get_authorization_service)
) -> None:
    """
    FastAPI dependency for route-level patient access validation.
    
    Usage in route:
        @router.get("/patients/{patient_id}/data")
        async def get_patient_data(
            patient_id: str,
            requester_id: str = Depends(get_current_user_id),
            _: None = Depends(require_patient_access_dependency)
        ):
            ...
    
    Args:
        patient_id: Patient ID from route path
        requester_id: Requester ID from auth token
        authorization_service: Injected authorization service
        
    Raises:
        PatientAccessDeniedException: If access is not allowed
    """
    await authorization_service.require_patient_access(requester_id, patient_id)


# =============================================================================
# Caregiver-Only Access Helpers
# =============================================================================
#
# These helpers operate directly on the `db` (Motor) instance to match the
# style used across the existing route modules (which take `db=Depends(get_database)`
# directly rather than going through the repository abstraction).
#
# Two distinct contracts:
#   - assert_data_access(): own-data OR caregiver-with-pairing. Used by existing
#     /health/patient/{id}/* routes to retrofit consistent access checks.
#   - require_caregiver_access(): caregiver-only. Blocks own-data path because
#     /caregiver/* endpoints are conceptually NOT for patients viewing themselves.
#


async def _query_active_pairing(db, caregiver_id: str, patient_id: str) -> Optional[Dict[str, Any]]:
    """Return the active pairing doc between caregiver and patient, or None."""
    return await db.pairings.find_one({
        "caregiverId": caregiver_id,
        "patientId": patient_id,
        "status": "active",
    })


async def assert_data_access(db, requester_id: str, target_patient_id: str) -> None:
    """
    Authorization rule applied to all patient-data endpoints.

    Access is granted when:
    - requester_id == target_patient_id (own data), OR
    - requester has an active caregiver pairing to target_patient_id

    Raises HTTP 403 otherwise.

    NOTE: This is the functional counterpart of the existing
    AuthorizationService.verify_patient_access() — it bypasses the repository
    abstraction so existing routes that already hold a `db` handle can adopt
    it without DI changes.
    """
    if requester_id == target_patient_id:
        return  # Own data

    pairing = await _query_active_pairing(db, requester_id, target_patient_id)
    if pairing is not None:
        return  # Active caregiver pairing

    logger.warning(
        f"Access denied: requester={requester_id} attempted to access "
        f"data of patient={target_patient_id} without an active pairing"
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Acceso no autorizado a datos de este usuario",
    )


def _safe_patient_view(user_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project only the safe fields a caregiver is allowed to see about a patient.
    Never exposes email, password, OAuth tokens, FCM token, etc.
    """
    return {
        "patient_id": str(user_doc.get("_id")),
        "name": user_doc.get("name"),
        "profile_picture": user_doc.get("profile_picture"),
    }


async def require_caregiver_access(
    patient_id: str,
    requester_id: str,
    db,
) -> Dict[str, Any]:
    """
    FastAPI-friendly authorization for /caregiver/ endpoints.

    Validates that:
      1. The patient_id is a valid ObjectId and the user exists.
      2. The requester is NOT the patient (caregiver-only path).
      3. An active pairing exists between requester (caregiver) and patient.

    Returns:
        A safe projection of the patient user document.

    Raises:
        404 if the patient does not exist.
        403 if the requester is the patient themselves, or has no active
            caregiver pairing with the patient.

    Usage:
        async def endpoint(
            patient_id: str,
            user_id: str = Depends(verify_token_jwt),
            db = Depends(get_database),
        ):
            patient = await require_caregiver_access(patient_id, user_id, db)
    """
    # Validate patient exists
    try:
        patient_oid = ObjectId(patient_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    patient = await db.users.find_one({"_id": patient_oid})
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    # Caregiver-only: requester must not be the patient
    if requester_id == patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido a cuidadores",
        )

    # Active pairing required
    pairing = await _query_active_pairing(db, requester_id, patient_id)
    if not pairing:
        logger.warning(
            f"Caregiver access denied: caregiver={requester_id} has no "
            f"active pairing with patient={patient_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este paciente",
        )

    return _safe_patient_view(patient)
