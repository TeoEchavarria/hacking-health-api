from fastapi import APIRouter, Depends, HTTPException, status, Header
from src.domains.auth.schemas import (
    LoginRequest, RefreshRequest, TokenResponse, SuccessResponse,
    OAuthTokenRequest, JWTTokenResponse, ErrorResponse, OpenWearablesCredentials
)
from src.core.database import get_database
from src.core.security import verify_password, get_password_hash, create_token
from src.core.jwt import (
    create_access_token, create_refresh_token, verify_access_token,
    verify_refresh_token, TokenExpiredError, TokenInvalidError,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from src.domains.auth.oauth_providers import (
    oauth_registry, TokenVerificationError, ProviderNotFoundError
)
from src.domains.openwearables.services import OpenWearablesService
from src._config.logger import get_logger
from src._config.settings import settings
from typing import Optional
from bson.objectid import ObjectId
import datetime

logger = get_logger(__name__)

router = APIRouter(tags=["auth"])


# =============================================================================
# OpenWearables Integration Helper
# =============================================================================

async def get_or_create_openwearables_credentials(
    user: dict,
    db
) -> Optional[OpenWearablesCredentials]:
    """
    Get or create OpenWearables credentials for a user.
    
    This function:
    1. Checks if user already has an OW user ID
    2. Creates OW user if not exists
    3. Generates SDK tokens
    4. Returns credentials for the mobile app
    
    Returns None if OpenWearables is not configured or fails.
    """
    # Skip if OpenWearables not properly configured
    if not settings.OPENWEARABLES_APP_SECRET or not settings.OPENWEARABLES_APP_ID:
        logger.debug("OpenWearables not configured (missing APP_ID or APP_SECRET)")
        return None
    
    try:
        service = OpenWearablesService()
        user_id = str(user["_id"])
        ow_user_id = user.get("open_wearables_user_id")
        
        if not ow_user_id:
            # Create user in OpenWearables
            ow_user = await service.create_user(
                external_user_id=user_id,
                email=user.get("email"),
                first_name=user.get("name", "").split()[0] if user.get("name") else None
            )
            ow_user_id = ow_user["id"]
            
            # Store mapping in our database
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"open_wearables_user_id": ow_user_id}}
            )
            logger.info(f"Created OpenWearables user {ow_user_id} for user {user_id}")
        
        # Generate SDK tokens
        tokens = await service.create_user_token(ow_user_id)
        
        return OpenWearablesCredentials(
            ow_user_id=ow_user_id,
            ow_access_token=tokens["access_token"],
            ow_refresh_token=tokens.get("refresh_token")
        )
        
    except Exception as e:
        # Log but don't fail the login - OW is optional
        logger.warning(f"Failed to get OpenWearables credentials: {e}")
        return None


# =============================================================================
# Authentication Dependencies
# =============================================================================

async def verify_token_jwt(
    authorization: Optional[str] = Header(None),
    db=Depends(get_database)
) -> str:
    """
    JWT-based token verification dependency.
    
    Verifies the JWT access token and returns the user_id.
    This is the new preferred authentication method.
    """
    # In DEV mode with DEBUG=True, allow bypass for testing
    if settings.DEBUG:
        test_user = await db.users.find_one()
        if test_user:
            logger.debug(f"[DEV MODE] Using test user: {test_user['_id']}")
            return str(test_user['_id'])
        
        # Create a test user if none exists
        hashed_password = get_password_hash('dev')
        new_user_result = await db.users.insert_one({
            'username': 'dev-test-user',
            'password': hashed_password,
            'families': [],
            'created_at': datetime.datetime.now(datetime.timezone.utc),
            'updated_at': datetime.datetime.now(datetime.timezone.utc)
        })
        test_user_id = str(new_user_result.inserted_id)
        logger.debug(f"[DEV MODE] Created and using test user: {test_user_id}")
        return test_user_id
    
    # Production mode - require valid JWT
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_token", "description": "No authorization header provided"}
        )
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_header", "description": "Authorization header must start with 'Bearer '"}
        )
    
    token = authorization[7:]  # Remove "Bearer " prefix
    
    try:
        payload = verify_access_token(token)
        user_id = payload["sub"]
        
        # Verify user still exists
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "user_not_found", "description": "User no longer exists"}
            )
        
        return user_id
        
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "token_expired", "description": "Access token has expired"}
        )
    except TokenInvalidError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "description": str(e)}
        )


async def verify_token(
    authorization: Optional[str] = Header(None),
    db=Depends(get_database)
) -> str:
    """
    Legacy token verification - supports both JWT and opaque tokens.
    
    This provides backward compatibility during migration.
    New endpoints should use verify_token_jwt instead.
    """
    # In DEV mode, return a default test user
    if settings.DEBUG:
        test_user = await db.users.find_one()
        if test_user:
            logger.debug(f"[DEV MODE] Using test user: {test_user['_id']}")
            return str(test_user['_id'])
        
        hashed_password = get_password_hash('dev')
        new_user_result = await db.users.insert_one({
            'username': 'dev-test-user',
            'password': hashed_password,
            'families': []
        })
        test_user_id = str(new_user_result.inserted_id)
        logger.debug(f"[DEV MODE] Created and using test user: {test_user_id}")
        return test_user_id
    
    if not authorization:
        raise HTTPException(status_code=400, detail='no token provided')
    
    try:
        token = authorization.split(' ')[1]
    except IndexError:
        raise HTTPException(status_code=400, detail='invalid authorization header format')
    
    # First try JWT verification
    try:
        payload = verify_access_token(token)
        return payload["sub"]
    except (TokenExpiredError, TokenInvalidError):
        pass  # Fall through to legacy verification
    
    # Fall back to legacy opaque token lookup
    user = await db.users.find_one({'token': token})
    
    if not user:
        raise HTTPException(status_code=403, detail='invalid token')
    
    if 'expiry' in user and datetime.datetime.now() > user['expiry']:
        raise HTTPException(status_code=403, detail='token expired. Use /login to reauthenticate.')
    
    return str(user['_id'])


# =============================================================================
# OAuth Endpoints
# =============================================================================

@router.post("/oauth/token", response_model=JWTTokenResponse, status_code=200)
async def oauth_token_exchange(
    request: OAuthTokenRequest,
    db=Depends(get_database)
):
    """
    Exchange an OAuth provider ID token for application tokens.
    
    This endpoint:
    1. Verifies the ID token with the OAuth provider
    2. Looks up or creates the user
    3. Links the OAuth provider to existing accounts (by email)
    4. Returns JWT access and refresh tokens
    
    Supports: Google (more providers can be added)
    """
    try:
        # Get the provider
        provider = oauth_registry.get_provider(request.provider)
    except ProviderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_provider", "description": str(e)}
        )
    
    try:
        # Verify the ID token with the provider
        user_info = await provider.verify_id_token(request.id_token)
        logger.info(f"OAuth token verified for {user_info.email} via {request.provider}")
    except TokenVerificationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "description": str(e)}
        )
    
    # Look up user by OAuth provider identity
    user = await db.users.find_one({
        "oauth_providers": {
            "$elemMatch": {
                "provider": request.provider,
                "provider_user_id": user_info.provider_user_id
            }
        }
    })
    
    now = datetime.datetime.now(datetime.timezone.utc)
    
    if not user:
        # Try to find existing user by email (for account linking)
        user = await db.users.find_one({"email": user_info.email})
        
        if user:
            # Link OAuth provider to existing account
            oauth_provider_doc = {
                "provider": request.provider,
                "provider_user_id": user_info.provider_user_id,
                "provider_email": user_info.email,
                "linked_at": now
            }
            
            await db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$push": {"oauth_providers": oauth_provider_doc},
                    "$set": {
                        "updated_at": now,
                        "email_verified": user_info.email_verified,
                        "profile_picture": user_info.picture
                    }
                }
            )
            logger.info(f"Linked {request.provider} to existing user {user['_id']}")
        else:
            # Create new user
            new_user_doc = {
                "username": user_info.email.split("@")[0],  # Default username from email
                "email": user_info.email,
                "email_verified": user_info.email_verified,
                "name": user_info.name,
                "profile_picture": user_info.picture,
                "password": None,  # OAuth-only users have no password
                "families": [],
                "oauth_providers": [{
                    "provider": request.provider,
                    "provider_user_id": user_info.provider_user_id,
                    "provider_email": user_info.email,
                    "linked_at": now
                }],
                "created_at": now,
                "updated_at": now
            }
            
            result = await db.users.insert_one(new_user_doc)
            user = await db.users.find_one({"_id": result.inserted_id})
            logger.info(f"Created new user {result.inserted_id} via {request.provider} OAuth")
    else:
        # Update last login and profile info
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {
                "updated_at": now,
                "profile_picture": user_info.picture,
                "name": user_info.name or user.get("name")
            }}
        )
    
    # Update FCM token if provided
    if request.fcm_token:
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"fcmToken": request.fcm_token}}
        )
    
    user_id = str(user["_id"])
    
    # Generate JWT tokens
    access_token = create_access_token(
        user_id=user_id,
        email=user_info.email,
        scopes=["profile", "health:read", "health:write"]
    )
    
    refresh_token, refresh_expiry = create_refresh_token(user_id=user_id)
    
    # Store refresh token hash for validation (optional, for revocation support)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "refresh_token_jti": refresh_token.split(".")[-1][:16],  # Store partial JTI for tracking
            "refresh_token_expiry": refresh_expiry
        }}
    )
    
    # Get OpenWearables credentials (non-blocking, optional)
    ow_credentials = await get_or_create_openwearables_credentials(user, db)
    
    return JWTTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        open_wearables=ow_credentials
    )


@router.get("/oauth/providers")
async def list_oauth_providers():
    """List available OAuth providers"""
    return {
        "providers": oauth_registry.list_providers()
    }


# =============================================================================
# Legacy Endpoints (maintained for backward compatibility)
# =============================================================================

@router.post("/login", response_model=TokenResponse, status_code=201)
async def login(request: LoginRequest, db=Depends(get_database)):
    """
    Legacy username/password login endpoint.
    
    Maintains backward compatibility while also supporting JWT tokens.
    New integrations should use /oauth/token for social login.
    """
    username = request.username
    password = request.password
    fcmToken = request.fcmToken

    user = await db.users.find_one({'username': username})
    now = datetime.datetime.now(datetime.timezone.utc)

    if not user:
        # Registration logic for new user
        hashed_password = get_password_hash(password)
        new_user_doc = {
            'username': username, 
            'password': hashed_password,
            'email': None,
            'families': [],
            'oauth_providers': [],
            'created_at': now,
            'updated_at': now
        }
        
        result = await db.users.insert_one(new_user_doc)
        user_id = str(result.inserted_id)
        
        # Get the created user for OpenWearables setup
        new_user = await db.users.find_one({"_id": result.inserted_id})
        
        # Generate JWT tokens
        access_token = create_access_token(user_id=user_id)
        refresh_token, expiry = create_refresh_token(user_id=user_id)
        
        # Get OpenWearables credentials for new user
        ow_credentials = await get_or_create_openwearables_credentials(new_user, db)

        return TokenResponse(
            token=access_token,
            refresh=refresh_token,
            expiry=expiry.isoformat(),
            open_wearables=ow_credentials
        )
    
    # Verify password
    if not user.get('password'):
        raise HTTPException(
            status_code=403, 
            detail='This account uses social login. Please sign in with Google.'
        )
    
    if not verify_password(password, user['password']):
        raise HTTPException(status_code=403, detail='invalid password')
   
    if fcmToken:
        try:
            await db.users.update_one({'username': username}, {"$set": {'fcmToken': fcmToken}})
        except Exception as e:
            logger.error(f"Failed to update FCM token: {e}")
            raise HTTPException(status_code=500, detail='failed to update fcm token')
    
    user_id = str(user['_id'])
    
    # Generate JWT tokens
    access_token = create_access_token(
        user_id=user_id,
        email=user.get('email')
    )
    refresh_token, expiry = create_refresh_token(user_id=user_id)
    
    # Update last login
    await db.users.update_one(
        {'_id': user['_id']}, 
        {"$set": {'updated_at': now}}
    )

    # Get OpenWearables credentials (non-blocking, optional)
    ow_credentials = await get_or_create_openwearables_credentials(user, db)

    return TokenResponse(
        token=access_token,
        refresh=refresh_token,
        expiry=expiry.isoformat(),
        open_wearables=ow_credentials
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest, db=Depends(get_database)):
    """
    Token refresh endpoint.
    
    Accepts a refresh token and returns new access and refresh tokens.
    Supports both JWT and legacy opaque refresh tokens.
    """
    refresh_token = request.refresh
    
    # Try JWT refresh token first
    try:
        payload = verify_refresh_token(refresh_token)
        user_id = payload["sub"]
        
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=403, detail='user not found')
        
        # Generate new tokens
        new_access_token = create_access_token(
            user_id=user_id,
            email=user.get('email')
        )
        new_refresh_token, expiry = create_refresh_token(user_id=user_id)
        
        return TokenResponse(
            token=new_access_token,
            refresh=new_refresh_token,
            expiry=expiry.isoformat()
        )
        
    except (TokenExpiredError, TokenInvalidError):
        pass  # Fall through to legacy handling
    
    # Legacy opaque token refresh
    user = await db.users.find_one({'refresh': refresh_token})

    if not user:
        raise HTTPException(status_code=403, detail='invalid refresh token')
    
    user_id = str(user['_id'])
    
    # Generate new JWT tokens
    new_access_token = create_access_token(
        user_id=user_id,
        email=user.get('email')
    )
    new_refresh_token, expiry = create_refresh_token(user_id=user_id)

    return TokenResponse(
        token=new_access_token,
        refresh=new_refresh_token,
        expiry=expiry.isoformat()
    )


@router.post("/logout", response_model=SuccessResponse)
async def logout(request: RefreshRequest, db=Depends(get_database)):
    """Invalidate a refresh token"""
    refresh_token = request.refresh
    
    # Try JWT token invalidation (mark in DB if needed)
    try:
        payload = verify_refresh_token(refresh_token)
        user_id = payload["sub"]
        
        # Clear refresh token tracking
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$unset": {"refresh_token_jti": "", "refresh_token_expiry": ""}}
        )
        return SuccessResponse(success=True)
        
    except (TokenExpiredError, TokenInvalidError):
        pass
    
    # Legacy opaque token logout
    await db.users.update_one(
        {'refresh': refresh_token}, 
        {"$unset": {'token': "", 'refresh': "", 'expiry': ""}}
    )
    
    return SuccessResponse(success=True)


@router.delete("/revoke", response_model=SuccessResponse)
async def revoke(user_id: str = Depends(verify_token), db=Depends(get_database)):
    """Revoke all tokens for the current user"""
    user = await db.users.find_one({'_id': ObjectId(user_id)})

    if not user:
        raise HTTPException(status_code=403, detail='invalid token')
    
    await db.users.update_one(
        {'_id': user['_id']}, 
        {"$unset": {
            'token': 1, 
            'refresh': 1, 
            'expiry': 1,
            'refresh_token_jti': 1,
            'refresh_token_expiry': 1
        }}
    )

    return SuccessResponse(success=True)
