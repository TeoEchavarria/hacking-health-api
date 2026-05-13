"""
Sync Request and Heart Rate History Routes.

Handles:
- On-demand sync requests from caregivers
- Pending sync checks from patient devices
- Sync completion confirmation
- Heart rate history queries

Following Single Responsibility Principle (SRP).
"""
from fastapi import APIRouter, HTTPException, Body, Depends, Query
from src.domains.health.schemas import (
    SyncRequestCreate, SyncRequestResponse, PendingSyncResponse,
    SyncCompleteInput, SyncCompleteResponse,
    HeartRateHistoryResponse
)
from src.domains.health.services import HealthService
from src.domains.auth.routes import verify_token_jwt
from src._config.logger import get_logger
from src.core.database import get_database

logger = get_logger(__name__)

router = APIRouter()


@router.post("/sync/request/{patient_id}", response_model=SyncRequestResponse)
async def create_sync_request(
    patient_id: str,
    request: SyncRequestCreate = Body(default=SyncRequestCreate()),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Create a sync request for a patient.
    Called by caregiver to request immediate sync from patient's device.

    The patient's device will poll for pending requests and sync when found.
    """
    try:
        service = HealthService(db)

        # Authorization: must be a caregiver for this patient
        has_access = await service.verify_patient_access(
            requester_id=user_id,
            patient_id=patient_id
        )

        if not has_access:
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para solicitar sync de este paciente"
            )

        # Create sync request
        result = await service.create_sync_request(
            patient_id=patient_id,
            requested_by=user_id,
            priority=request.priority
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating sync request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/pending", response_model=PendingSyncResponse)
async def get_pending_sync_request(
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Check for pending sync requests for the current user.
    Called by patient's device to check if sync is needed.

    Returns the oldest pending request if any.
    """
    try:
        service = HealthService(db)
        result = await service.get_pending_sync_request(patient_id=user_id)
        return result

    except Exception as e:
        logger.error(f"Error checking pending sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/complete", response_model=SyncCompleteResponse)
async def complete_sync_request(
    request: SyncCompleteInput,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Mark a sync request as complete.
    Called by patient's device after syncing data.
    """
    try:
        service = HealthService(db)
        result = await service.complete_sync_request(
            request_id=request.request_id,
            metrics_synced=request.metrics_synced
        )
        return result

    except Exception as e:
        logger.error(f"Error completing sync request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patient/{patient_id}/heart-rate-history", response_model=HeartRateHistoryResponse)
async def get_patient_heart_rate_history(
    patient_id: str,
    days: int = Query(7, ge=1, le=30, description="Number of days of history (1-30)"),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get heart rate history for a patient.

    Returns daily aggregated heart rate data (avg, min, max, sample count).

    AUTHORIZATION:
    - If user_id == patient_id: User accessing own history
    - Otherwise: Must have active pairing as caregiver
    """
    try:
        service = HealthService(db)

        # Authorization check
        has_access = await service.verify_patient_access(
            requester_id=user_id,
            patient_id=patient_id
        )

        if not has_access:
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para ver el historial de este paciente"
            )

        # Fetch history
        result = await service.get_patient_heart_rate_history(
            patient_id=patient_id,
            days=days
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching heart rate history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
