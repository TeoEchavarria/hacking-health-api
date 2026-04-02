from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class LoginRequest(BaseModel):
    username: str
    password: str
    fcmToken: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh: str


class OpenWearablesCredentials(BaseModel):
    """OpenWearables SDK credentials"""
    ow_user_id: Optional[str] = Field(default=None, description="OpenWearables user ID")
    ow_access_token: Optional[str] = Field(default=None, description="OpenWearables access token")
    ow_refresh_token: Optional[str] = Field(default=None, description="OpenWearables refresh token")


class TokenResponse(BaseModel):
    """Legacy token response for backward compatibility"""
    token: str
    refresh: str
    expiry: str
    # OpenWearables credentials (optional, included when available)
    open_wearables: Optional[OpenWearablesCredentials] = None


class JWTTokenResponse(BaseModel):
    """OAuth2-compliant token response"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
    # OpenWearables credentials (optional, included when available)
    open_wearables: Optional[OpenWearablesCredentials] = None


class OAuthTokenRequest(BaseModel):
    """Request to exchange OAuth provider token for app tokens"""
    provider: str = Field(description="OAuth provider name (e.g., 'google', 'github')")
    id_token: str = Field(description="ID token from the OAuth provider")
    device_info: Optional[dict] = Field(default=None, description="Optional device information")
    fcm_token: Optional[str] = Field(default=None, description="Firebase Cloud Messaging token")


class OAuthProvider(BaseModel):
    """OAuth provider information linked to a user"""
    provider: str
    provider_user_id: str
    provider_email: str
    linked_at: datetime


class SuccessResponse(BaseModel):
    success: bool


class ErrorResponse(BaseModel):
    error: str
    description: Optional[str] = None


class UserInfoResponse(BaseModel):
    """User info extracted from OAuth token"""
    id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    providers: List[str] = []

