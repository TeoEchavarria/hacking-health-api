from fastapi import APIRouter, Depends, HTTPException, status, Header
from src.domains.auth.schemas import LoginRequest, RefreshRequest, TokenResponse, SuccessResponse
from src.core.database import get_database
from src.core.security import verify_password, get_password_hash, create_token
from src._config.logger import get_logger
from src._config.settings import settings
from typing import Optional
from bson.objectid import ObjectId
import datetime

logger = get_logger(__name__)

router = APIRouter(tags=["auth"])

# Auth dependency
async def verify_token(authorization: Optional[str] = Header(None), db=Depends(get_database)) -> str:
    # In DEV mode, return a default test user if configured
    if settings.DEBUG:
        # Try to find the first user, or create a test user if none exists
        test_user = await db.users.find_one()
        if test_user:
            logger.debug(f"[DEV MODE] Using test user: {test_user['_id']}")
            return str(test_user['_id'])
        
        # Create a test user if no users exist
        hashed_password = get_password_hash('dev')
        new_user_result = await db.users.insert_one({
            'username': 'dev-test-user',
            'password': hashed_password,
            'families': []
        })
        test_user_id = str(new_user_result.inserted_id)
        logger.debug(f"[DEV MODE] Created and using test user: {test_user_id}")
        return test_user_id
    
    # Production mode - require valid authorization
    if not authorization:
        raise HTTPException(status_code=400, detail='no token provided')
    
    try:
        token = authorization.split(' ')[1]
    except IndexError:
        raise HTTPException(status_code=400, detail='invalid authorization header format')

    user = await db.users.find_one({'token': token})

    if not user:
        raise HTTPException(status_code=403, detail='invalid token')
    
    if 'expiry' in user and datetime.datetime.now() > user['expiry']:
        raise HTTPException(status_code=403, detail='token expired. Use /login to reauthenticate.')
    
    return str(user['_id'])

@router.post("/login", response_model=TokenResponse, status_code=201)
async def login(request: LoginRequest, db=Depends(get_database)):
    username = request.username
    password = request.password
    fcmToken = request.fcmToken

    user = await db.users.find_one({'username': username})

    if not user:
        # Registration logic for new user
        hashed_password = get_password_hash(password)
        new_user_doc = {'username': username, 'password': hashed_password}
        
        # Insert and get ID
        result = await db.users.insert_one(new_user_doc)
        user_id = result.inserted_id
        
        token = create_token()
        refresh = create_token()
        expiryDate = datetime.datetime.now() + datetime.timedelta(hours=12)
        
        await db.users.update_one(
            {'_id': user_id}, 
            {"$set": {'token': token, 'refresh': refresh, 'expiry': expiryDate}}
        )

        return TokenResponse(
            token=token,
            refresh=refresh,
            expiry=expiryDate.isoformat()
        )
    
    # Verify password
    if not verify_password(password, user['password']):
        raise HTTPException(status_code=403, detail='invalid password')
   
    if fcmToken:
        try:
            await db.users.update_one({'username': username}, {"$set": {'fcmToken': fcmToken}})
        except Exception as e:
            logger.error(f"Failed to update FCM token: {e}")
            raise HTTPException(status_code=500, detail='failed to update fcm token')
        
    sessid = user['_id']

    if "expiry" not in user or datetime.datetime.now() > user['expiry']:
        token = create_token()
        refresh = create_token()
        expiryDate = datetime.datetime.now() + datetime.timedelta(hours=12)
        await db.users.update_one({'_id': sessid}, {"$set": {'token': token, 'refresh': refresh, 'expiry': expiryDate}})
    else:
        token = user.get('token')
        refresh = user.get('refresh')
        expiryDate = user.get('expiry')
        
        # Handle case where existing user might not have these fields
        if not token or not refresh or not expiryDate:
            token = create_token()
            refresh = create_token()
            expiryDate = datetime.datetime.now() + datetime.timedelta(hours=12)
            await db.users.update_one({'_id': sessid}, {"$set": {'token': token, 'refresh': refresh, 'expiry': expiryDate}})

    return TokenResponse(
        token=token,
        refresh=refresh,
        expiry=expiryDate.isoformat()
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest, db=Depends(get_database)):
    refresh_token = request.refresh

    user = await db.users.find_one({'refresh': refresh_token})

    if not user:
        raise HTTPException(status_code=403, detail='invalid refresh token')
    
    token = create_token()
    # refresh = create_token() # disable refresh token rotation- design flaw, see #35
    expiryDate = datetime.datetime.now() + datetime.timedelta(hours=12)
    
    await db.users.update_one(
        {'_id': user['_id']}, 
        {"$set": {'token': token, 'refresh': refresh_token, 'expiry': expiryDate}}
    )

    return TokenResponse(
        token=token,
        refresh=refresh_token,
        expiry=expiryDate.isoformat()
    )

@router.delete("/revoke", response_model=SuccessResponse)
async def revoke(user_id: str = Depends(verify_token), db=Depends(get_database)):
    user = await db.users.find_one({'_id': ObjectId(user_id)})

    if not user:
        raise HTTPException(status_code=403, detail='invalid token')
    
    await db.users.update_one({'_id': user['_id']}, {"$unset": {'token': 1, 'refresh': 1, 'expiry': 1}})

    return SuccessResponse(success=True)
