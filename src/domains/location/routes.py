"""
FastAPI routes for location tracking and sharing endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from src.domains.location.schemas import (
    LocationUpdateRequest,
    LocationUpdateResponse,
    PairedLocationResponse,
    LocationResponse,
    SharingToggleRequest,
    SharingStatusResponse,
    LocationHistoryResponse,
    RelationLocationsResponse,
    UserLocationInfo,
    PartnerLocationInfo,
    LocationCoordinates
)
from src.domains.location.services import LocationService
from src.domains.auth.routes import verify_token_jwt
from src.core.database import get_database
from src._config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/location", tags=["location"])


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/update",
    response_model=LocationUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update my location",
    description="Store the current user's GPS location for sharing with paired user."
)
async def update_location(
    request: LocationUpdateRequest,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Update the authenticated user's current location.
    
    This endpoint should be called periodically (e.g., every 5 minutes)
    by the mobile app's location sync service.
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Request Body:**
    - latitude: GPS latitude (-90 to 90)
    - longitude: GPS longitude (-180 to 180)
    - accuracy: Optional GPS accuracy in meters
    - timestamp: Optional client-side timestamp in milliseconds
    
    **Returns:**
    - success: Boolean indicating success
    - updatedAt: Server timestamp in milliseconds
    """
    try:
        service = LocationService(db)
        result = await service.update_location(
            user_id=user_id,
            latitude=request.latitude,
            longitude=request.longitude,
            accuracy=request.accuracy,
            client_timestamp=request.timestamp
        )
        
        return LocationUpdateResponse(
            success=result["success"],
            updatedAt=result["updated_at"]
        )
    
    except Exception as e:
        logger.error(f"Error updating location for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar ubicación"
        )


@router.get(
    "/paired",
    response_model=RelationLocationsResponse,
    summary="Get self and paired user locations",
    description="Get both your location and your paired user's location for map display."
)
async def get_paired_location(
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get location data for both self and paired user.
    
    This returns a comprehensive response including:
    - self: Your own location info
    - partner: Paired user's location with stale detection
    - hasRelation: Whether you have an active pairing
    - message: Optional explanation
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Returns:**
    - self: UserLocationInfo with name, avatar, role, location, sharingEnabled
    - partner: PartnerLocationInfo with locationStale flag (true if > 15 min old)
    - hasRelation: Boolean indicating if an active pairing exists
    - message: Explanation (if no relation or error)
    """
    try:
        service = LocationService(db)
        result = await service.get_paired_user_location(user_id)
        
        # Build self info
        self_info = None
        if result.get("self"):
            s = result["self"]
            self_location = None
            if s.get("location"):
                loc = s["location"]
                self_location = LocationCoordinates(
                    latitude=loc["latitude"],
                    longitude=loc["longitude"],
                    accuracy=loc.get("accuracy"),
                    updatedAt=loc.get("updatedAt")
                )
            self_info = UserLocationInfo(
                name=s["name"],
                avatar=s.get("avatar"),
                role=s.get("role", "patient"),
                location=self_location,
                sharingEnabled=s.get("sharingEnabled", True)
            )
        
        # Build partner info
        partner_info = None
        if result.get("partner"):
            p = result["partner"]
            partner_location = None
            if p.get("location"):
                loc = p["location"]
                partner_location = LocationCoordinates(
                    latitude=loc["latitude"],
                    longitude=loc["longitude"],
                    accuracy=loc.get("accuracy"),
                    updatedAt=loc.get("updatedAt")
                )
            partner_info = PartnerLocationInfo(
                name=p["name"],
                avatar=p.get("avatar"),
                role=p.get("role", "patient"),
                location=partner_location,
                locationStale=p.get("locationStale", False),
                lastSeenAt=p.get("lastSeenAt"),
                sharingEnabled=p.get("sharingEnabled", True),
                sharingDisabledMessage=p.get("sharingDisabledMessage")
            )
        
        return RelationLocationsResponse(
            self_info=self_info,
            partner=partner_info,
            hasRelation=result.get("hasRelation", False),
            message=result.get("message")
        )
    
    except Exception as e:
        logger.error(f"Error getting paired location for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener ubicación del usuario vinculado"
        )


@router.patch(
    "/sharing",
    response_model=SharingStatusResponse,
    summary="Toggle location sharing",
    description="Enable or disable sharing your location with your paired user."
)
async def toggle_sharing(
    request: SharingToggleRequest,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Toggle location sharing preference.
    
    When disabled, your paired user will not be able to see your location.
    Default is enabled (True).
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Request Body:**
    - sharingEnabled: Boolean to enable/disable sharing
    
    **Returns:**
    - sharingEnabled: Updated sharing status
    """
    try:
        service = LocationService(db)
        result = await service.toggle_sharing(user_id, request.sharing_enabled)
        
        return SharingStatusResponse(sharingEnabled=result["sharing_enabled"])
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error toggling sharing for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar preferencia de compartir"
        )


@router.get(
    "/sharing",
    response_model=SharingStatusResponse,
    summary="Get sharing status",
    description="Get current location sharing preference."
)
async def get_sharing_status(
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get the current location sharing status.
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Returns:**
    - sharingEnabled: Current sharing status
    """
    try:
        service = LocationService(db)
        result = await service.get_sharing_status(user_id)
        
        return SharingStatusResponse(sharingEnabled=result["sharing_enabled"])
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting sharing status for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estado de compartir"
        )


@router.get(
    "/history",
    response_model=LocationHistoryResponse,
    summary="Get my location history",
    description="Get your own location history for the past 24 hours."
)
async def get_location_history(
    hours: int = 24,
    limit: int = 100,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get the authenticated user's location history.
    
    **Authentication Required:** Bearer token in Authorization header
    
    **Query Parameters:**
    - hours: Number of hours to look back (default: 24)
    - limit: Maximum locations to return (default: 100)
    
    **Returns:**
    - userId: User ID
    - locations: List of location records
    """
    try:
        # Clamp values to reasonable ranges
        hours = min(max(1, hours), 168)  # 1 hour to 7 days
        limit = min(max(1, limit), 500)
        
        service = LocationService(db)
        locations = await service.get_location_history(user_id, hours, limit)
        
        return LocationHistoryResponse(
            userId=user_id,
            locations=[
                LocationResponse(
                    userId=loc["user_id"],
                    userName="",  # Own history, name not needed
                    latitude=loc["latitude"],
                    longitude=loc["longitude"],
                    accuracy=loc.get("accuracy"),
                    updatedAt=loc["updated_at"]
                )
                for loc in locations
            ]
        )
    
    except Exception as e:
        logger.error(f"Error getting location history for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener historial de ubicación"
        )
