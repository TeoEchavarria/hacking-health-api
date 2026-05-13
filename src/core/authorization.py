"""
Authorization service for patient data access control.

Centralizes authorization logic to avoid duplication across domains.
Follows Single Responsibility Principle and DRY (Don't Repeat Yourself).
"""

import logging
from typing import Optional
from fastapi import Depends, HTTPException, Header

from src.core.repositories.pairing_repository import IPairingRepository
from src.core.exceptions import PatientAccessDeniedException


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
