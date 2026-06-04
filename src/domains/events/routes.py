"""
Routes for biometric events.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from src.domains.events.schemas import (
    EventsListResponse,
    UnreadCountResponse,
    ManualAlertRequest,
    BiometricEventType,
)
from src.domains.events.services import BiometricEventService
from src.domains.auth.routes import verify_token_jwt
from src.core.database import get_database
from src._config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/events",
    tags=["events"]
)


@router.get("/me", response_model=EventsListResponse)
async def get_my_events(
    limit: int = Query(default=20, ge=1, le=100, description="Events per page"),
    page: int = Query(default=1, ge=1, description="Page number"),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get biometric events for the authenticated user.
    
    Returns events where the user is either the patient or the caregiver.
    Events are sorted by recordedAt descending (most recent first).
    
    Calling this endpoint marks returned events as read for the user.
    
    - If user is the patient: readByPatient is set to true
    - If user is the caregiver: readByCaregiver is set to true
    """
    try:
        service = BiometricEventService(db)
        result = await service.get_events_for_user(
            user_id=user_id,
            limit=limit,
            page=page
        )
        return result
        
    except Exception as e:
        logger.error(f"Error fetching events for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error al cargar los eventos"
        )


@router.get("/me/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get count of unread events for the authenticated user.
    
    Counts events where:
    - User is patient AND readByPatient is false, OR
    - User is caregiver AND readByCaregiver is false
    """
    try:
        service = BiometricEventService(db)
        count = await service.get_unread_count(user_id)
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error getting unread count for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error al obtener el conteo de no leídos"
        )


@router.post("/manual-alert")
async def create_manual_alert(
    body: ManualAlertRequest,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Patient-triggered manual/emergency alert (the "Urgencia" button).

    Registers a MANUAL_ALERT biometric event for the authenticated patient.
    register_biometric_event resolves the active pairing and pushes the alert
    to the caregiver automatically.
    """
    try:
        service = BiometricEventService(db)
        message = body.message or "🚨 Solicitó ayuda urgente"
        event = await service.register_biometric_event(
            patient_id=user_id,
            event_type=BiometricEventType.MANUAL_ALERT.value,
            payload={
                "message": message,
                "severity": body.severity.value,
                "source": "emergency_button",
            },
        )
        return {"success": True, "event_id": str(event.get("_id"))}

    except Exception as e:
        logger.error(f"Error creating manual alert for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error al enviar la alerta de urgencia"
        )
