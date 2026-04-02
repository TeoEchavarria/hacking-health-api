from fastapi import APIRouter, Depends, HTTPException
from src.core.database import get_database
from src.domains.auth.routes import verify_token_jwt
from src.domains.openwearables.schemas import (
    OpenWearablesCredentials,
    ConnectionStatus
)
from src.domains.openwearables.services import OpenWearablesService
from src._config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/openwearables", tags=["OpenWearables"])


@router.post("/connect", response_model=OpenWearablesCredentials)
async def connect_health(
    current_user: dict = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Connect user to OpenWearables for health data sync.
    
    This endpoint:
    1. Gets or creates an OpenWearables user for the authenticated user
    2. Generates SDK tokens (access_token + refresh_token)
    3. Returns credentials for the mobile SDK to use
    
    The mobile app should call this endpoint, then use the returned
    credentials to initialize the OpenWearables SDK.
    """
    service = OpenWearablesService()
    user_id = str(current_user["_id"])
    
    # Check if user already has OpenWearables user ID
    ow_user_id = current_user.get("open_wearables_user_id")
    
    if not ow_user_id:
        # Create user in OpenWearables
        try:
            ow_user = await service.create_user(
                external_user_id=user_id,
                email=current_user.get("email")
            )
            ow_user_id = ow_user["id"]
            
            # Store mapping in our database
            await db.users.update_one(
                {"_id": current_user["_id"]},
                {"$set": {"open_wearables_user_id": ow_user_id}}
            )
            logger.info(f"Linked user {user_id} to OW user {ow_user_id}")
            
        except Exception as e:
            logger.error(f"Failed to create OpenWearables user: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to create health data connection"
            )
    
    # Generate SDK tokens
    try:
        tokens = await service.create_user_token(ow_user_id)
        
        return OpenWearablesCredentials(
            userId=ow_user_id,
            accessToken=tokens["access_token"],
            refreshToken=tokens.get("refresh_token")
        )
        
    except Exception as e:
        logger.error(f"Failed to generate tokens: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate health sync credentials"
        )


@router.get("/status", response_model=ConnectionStatus)
async def get_connection_status(
    current_user: dict = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get the current health data connection status for the user.
    
    Returns whether the user is connected to OpenWearables and
    information about their last sync.
    """
    service = OpenWearablesService()
    ow_user_id = current_user.get("open_wearables_user_id")
    
    if not ow_user_id:
        return ConnectionStatus(connected=False)
    
    # Get user details from OpenWearables
    try:
        ow_user = await service.get_user(ow_user_id)
        
        if ow_user:
            return ConnectionStatus(
                connected=True,
                openWearablesUserId=ow_user_id,
                lastSyncedAt=ow_user.get("last_synced_at"),
                lastSyncedProvider=ow_user.get("last_synced_provider")
            )
        else:
            # User not found in OW, clear the link
            await db.users.update_one(
                {"_id": current_user["_id"]},
                {"$unset": {"open_wearables_user_id": ""}}
            )
            return ConnectionStatus(connected=False)
            
    except Exception as e:
        logger.error(f"Failed to get OW user status: {e}")
        return ConnectionStatus(
            connected=True,
            openWearablesUserId=ow_user_id
        )


@router.post("/disconnect")
async def disconnect_health(
    current_user: dict = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Disconnect user from OpenWearables.
    
    This removes the link between your user and OpenWearables.
    Note: This does NOT delete the user's data in OpenWearables.
    """
    ow_user_id = current_user.get("open_wearables_user_id")
    
    if not ow_user_id:
        return {"message": "Not connected"}
    
    # Remove the link in our database
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$unset": {"open_wearables_user_id": ""}}
    )
    
    logger.info(f"Disconnected user {current_user['_id']} from OW")
    
    return {"message": "Disconnected successfully"}


@router.get("/health-data")
async def get_health_data(
    data_type: str = None,
    from_date: str = None,
    to_date: str = None,
    current_user: dict = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Query health data for the authenticated user.
    
    Args:
        data_type: Optional filter by type (e.g., "heart_rate", "steps", "sleep")
        from_date: Optional start date (ISO format)
        to_date: Optional end date (ISO format)
    
    Returns:
        Health data records from OpenWearables
    """
    service = OpenWearablesService()
    ow_user_id = current_user.get("open_wearables_user_id")
    
    if not ow_user_id:
        raise HTTPException(
            status_code=400,
            detail="User not connected to health data. Call /connect first."
        )
    
    try:
        data = await service.get_user_health_data(
            user_id=ow_user_id,
            data_type=data_type,
            from_date=from_date,
            to_date=to_date
        )
        return data
        
    except Exception as e:
        logger.error(f"Failed to get health data: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve health data"
        )
