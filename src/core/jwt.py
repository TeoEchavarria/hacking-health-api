"""
JWT Token Management Module

This module provides JWT-based authentication tokens for the application.
Uses RS256 (asymmetric signing) for future microservices compatibility.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import jwt, JWTError, ExpiredSignatureError
from src._config.settings import settings
from src._config.logger import get_logger
import uuid

logger = get_logger(__name__)

# JWT Configuration
ALGORITHM = "HS256"  # Using symmetric for simplicity, can migrate to RS256 for microservices
ISSUER = "hacking-health-api"
AUDIENCE = "hacking-health-app"

# Token lifetimes
ACCESS_TOKEN_EXPIRE_MINUTES = 10080  # 7 days
REFRESH_TOKEN_EXPIRE_DAYS = 30  # 30 days


class TokenError(Exception):
    """Base exception for token-related errors"""
    pass


class TokenExpiredError(TokenError):
    """Raised when a token has expired"""
    pass


class TokenInvalidError(TokenError):
    """Raised when a token is invalid"""
    pass


def create_access_token(
    user_id: str,
    email: Optional[str] = None,
    scopes: Optional[list] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token for a user.
    
    Args:
        user_id: The unique identifier of the user
        email: User's email address
        scopes: List of permission scopes
        expires_delta: Custom expiration time (default: 15 minutes)
    
    Returns:
        Encoded JWT access token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    
    payload = {
        "sub": user_id,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access"
    }
    
    if email:
        payload["email"] = email
    
    if scopes:
        payload["scopes"] = scopes
    else:
        payload["scopes"] = ["profile", "health:read", "health:write"]
    
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Created access token for user {user_id}, expires at {expire.isoformat()}")
    
    return token


def create_refresh_token(
    user_id: str,
    expires_delta: Optional[timedelta] = None
) -> tuple[str, datetime]:
    """
    Create a JWT refresh token for a user.
    
    Args:
        user_id: The unique identifier of the user
        expires_delta: Custom expiration time (default: 7 days)
    
    Returns:
        Tuple of (encoded JWT refresh token string, expiration datetime)
    """
    if expires_delta is None:
        expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    
    payload = {
        "sub": user_id,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "refresh"
    }
    
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Created refresh token for user {user_id}, expires at {expire.isoformat()}")
    
    return token, expire


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT access token.
    
    Args:
        token: The JWT access token to verify
    
    Returns:
        Decoded token payload as dictionary
    
    Raises:
        TokenExpiredError: If the token has expired
        TokenInvalidError: If the token is invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER
        )
        
        # Verify token type
        if payload.get("type") != "access":
            raise TokenInvalidError("Invalid token type: expected access token")
        
        return payload
        
    except ExpiredSignatureError:
        logger.warning("Access token expired")
        raise TokenExpiredError("Access token has expired")
    except JWTError as e:
        logger.warning(f"Invalid access token: {e}")
        raise TokenInvalidError(f"Invalid access token: {str(e)}")


def verify_refresh_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT refresh token.
    
    Args:
        token: The JWT refresh token to verify
    
    Returns:
        Decoded token payload as dictionary
    
    Raises:
        TokenExpiredError: If the token has expired
        TokenInvalidError: If the token is invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER
        )
        
        # Verify token type
        if payload.get("type") != "refresh":
            raise TokenInvalidError("Invalid token type: expected refresh token")
        
        return payload
        
    except ExpiredSignatureError:
        logger.warning("Refresh token expired")
        raise TokenExpiredError("Refresh token has expired")
    except JWTError as e:
        logger.warning(f"Invalid refresh token: {e}")
        raise TokenInvalidError(f"Invalid refresh token: {str(e)}")


def decode_token_unsafe(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode a JWT token WITHOUT verification.
    Useful for debugging or reading non-sensitive claims.
    
    WARNING: Do NOT use this for authentication decisions.
    
    Args:
        token: The JWT token to decode
    
    Returns:
        Decoded token payload or None if decoding fails
    """
    try:
        # Decode without verification
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_signature": False, "verify_exp": False, "verify_aud": False, "verify_iss": False}
        )
        return payload
    except Exception as e:
        logger.debug(f"Failed to decode token (unsafe): {e}")
        return None


def get_token_expiry(token: str) -> Optional[datetime]:
    """
    Get the expiration time of a token without full verification.
    
    Args:
        token: The JWT token
    
    Returns:
        Expiration datetime or None if cannot be determined
    """
    payload = decode_token_unsafe(token)
    if payload and "exp" in payload:
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    return None
