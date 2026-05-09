"""
FastAPI routes for pairing (family linking) endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from src.domains.pairing.schemas import (
    CreatePairingCodeRequest,
    CreatePairingCodeResponse,
    ValidatePairingCodeRequest,
    ValidatePairingCodeResponse,
    PairingStatusResponse,
    RevokePairingResponse,
    MyPairingInfo,
    MyPairingsResponse
)
from src.domains.pairing.services import PairingService
from src.domains.auth.routes import verify_token_jwt
from src.core.database import get_database
from src._config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/pairing", tags=["pairing"])


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/create",
    response_model=CreatePairingCodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create pairing code",
    description="Generate a 6-digit code for family linking (patient side). Code expires in 10 minutes."
)
async def create_pairing_code(
    request: CreatePairingCodeRequest,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Create a new pairing code for a patient.
    
    The patient generates this code and shares it with their caregiver.
    The code is valid for 10 minutes.
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Returns:**
    - pairing_id: Unique identifier for this pairing
    - code: 6-digit numeric code to share with caregiver
    - created_at: Unix timestamp (milliseconds)
    - expires_at: Unix timestamp (milliseconds)
    """
    try:
        service = PairingService(db)
        result = await service.create_pairing_code(user_id)
        
        logger.info(f"User {user_id} created pairing code")
        
        return CreatePairingCodeResponse(
            pairingId=result["pairing_id"],
            code=result["code"],
            createdAt=result["created_at"],
            expiresAt=result["expires_at"]
        )
    
    except ValueError as e:
        logger.error(f"Validation error creating pairing code: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating pairing code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al generar código de vinculación"
        )


@router.post(
    "/validate",
    response_model=ValidatePairingCodeResponse,
    summary="Validate pairing code",
    description="Validate a 6-digit code and activate family pairing (caregiver side)."
)
async def validate_pairing_code(
    request: ValidatePairingCodeRequest,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Validate a pairing code and activate the family link.
    
    The caregiver enters the 6-digit code received from the patient.
    If valid and not expired, the pairing is activated.
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Request Body:**
    - code: 6-digit numeric code
    
    **Returns:**
    - success: Whether validation succeeded
    - pairing_id: ID of the activated pairing (if success)
    - patient_id: ID of the linked patient (if success)
    - patient_name: Name of the linked patient (if success)
    - error: Error message (if not success)
    """
    try:
        service = PairingService(db)
        result = await service.validate_pairing_code(request.code, user_id)
        
        if result["success"]:
            logger.info(
                f"User {user_id} (caregiver) paired with patient {result['patient_id']}"
            )
        else:
            logger.warning(f"Failed pairing validation for code {request.code}: {result.get('error')}")
        
        return ValidatePairingCodeResponse(
            success=result["success"],
            pairingId=result.get("pairing_id"),
            patientId=result.get("patient_id"),
            patientName=result.get("patient_name"),
            error=result.get("error")
        )
    
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error validating pairing code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al validar código"
        )


@router.get(
    "/{pairingId}/status",
    response_model=PairingStatusResponse,
    summary="Check pairing status",
    description="Get the current status of a pairing (used for polling by patient)."
)
async def get_pairing_status(
    pairingId: str,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get the current status of a pairing.
    
    Used by the patient to poll and detect when the caregiver has
    entered the code and activated the pairing.
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Path Parameters:**
    - pairingId: ID of the pairing to check
    
    **Returns:**
    - pairing_id: ID of the pairing
    - status: Current status ("pending", "active", "expired")
    - linked: Whether the pairing is active
    - caregiver_id: ID of caregiver (if linked)
    - caregiver_name: Name of caregiver (if linked)
    - patient_id: ID of patient
    - patient_name: Name of patient
    - created_at: Unix timestamp (milliseconds)
    - expires_at: Unix timestamp (milliseconds, null if activated)
    - activated_at: Unix timestamp (milliseconds, null if not activated)
    """
    try:
        service = PairingService(db)
        result = await service.get_pairing_status(pairingId)
        
        # Verify user has access to this pairing
        if result["patient_id"] != user_id and result.get("caregiver_id") != user_id:
            logger.warning(f"User {user_id} attempted to access pairing {pairingId}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para acceder a este pairing"
            )
        
        return PairingStatusResponse(
            pairingId=result["pairing_id"],
            status=result["status"],
            linked=result["linked"],
            caregiverId=result["caregiver_id"],
            caregiverName=result["caregiver_name"],
            patientId=result["patient_id"],
            patientName=result["patient_name"],
            createdAt=result["created_at"],
            expiresAt=result["expires_at"],
            activatedAt=result["activated_at"]
        )
    
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pairing status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estado del pairing"
        )


@router.get(
    "/user/list",
    summary="List user pairings",
    description="Get all active pairings for the authenticated user."
)
async def list_user_pairings(
    role: str = "patient",
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    List all active pairings for a user.
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Query Parameters:**
    - role: "patient" or "caregiver" (default: "patient")
    
    **Returns:**
    List of pairing documents
    """
    if role not in ["patient", "caregiver"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'patient' or 'caregiver'"
        )
    
    try:
        service = PairingService(db)
        pairings = await service.get_user_pairings(user_id, role)
        
        logger.info(f"Retrieved {len(pairings)} pairings for user {user_id} as {role}")
        
        return {
            "success": True,
            "count": len(pairings),
            "pairings": pairings
        }
    
    except Exception as e:
        logger.error(f"Error listing user pairings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al listar vinculaciones"
        )


@router.get(
    "/me",
    response_model=MyPairingsResponse,
    summary="Get my active pairings",
    description="Get all active pairings for the authenticated user, regardless of role."
)
async def get_my_pairings(
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get all active pairings where the authenticated user is either patient or caregiver.
    
    This endpoint is designed for session initialization - it returns all active
    relationships without requiring the caller to specify a role.
    
    Returns an empty array (not 404) if the user has no active pairings.
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Returns:**
    - pairings: List of active pairings with role and other user's info
    - count: Number of active pairings
    
    Each pairing includes:
    - pairingId: Unique identifier
    - role: User's role in this pairing ("caregiver" or "patient")
    - otherUserId: ID of the linked user
    - otherUserName: Name of the linked user
    - otherUserProfilePicture: Profile picture URL of the linked user (if available)
    - status: Always "active" for this endpoint
    - activatedAt: When the pairing was activated (ms timestamp)
    - createdAt: When the pairing was created (ms timestamp)
    """
    try:
        service = PairingService(db)
        pairings = await service.get_my_pairings(user_id)
        
        logger.info(f"User {user_id} retrieved {len(pairings)} active pairings via /me")
        
        return MyPairingsResponse(
            pairings=[MyPairingInfo(**p) for p in pairings],
            count=len(pairings)
        )
    
    except Exception as e:
        logger.error(f"Error getting my pairings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener vinculaciones"
        )


@router.post(
    "/{pairingId}/revoke",
    response_model=RevokePairingResponse,
    summary="Revoke a pairing",
    description="Revoke an active pairing. User must be patient or caregiver in the pairing."
)
async def revoke_pairing(
    pairingId: str,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Revoke an active family pairing.
    
    Either the patient or caregiver can revoke the pairing.
    The pairing is marked as "revoked" (not deleted) for audit trail.
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Path Parameters:**
    - pairingId: ID of the pairing to revoke
    
    **Returns:**
    - success: Whether revocation succeeded
    - message: Success message (if success)
    - error: Error message (if not success)
    """
    try:
        service = PairingService(db)
        result = await service.revoke_pairing(pairingId, user_id)
        
        if result["success"]:
            logger.info(f"User {user_id} revoked pairing {pairingId}")
        else:
            logger.warning(f"Failed to revoke pairing {pairingId}: {result.get('error')}")
        
        return RevokePairingResponse(
            success=result["success"],
            message=result.get("message"),
            error=result.get("error")
        )
    
    except Exception as e:
        logger.error(f"Error revoking pairing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al revocar vinculación"
        )
