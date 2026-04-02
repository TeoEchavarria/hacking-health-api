from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class OpenWearablesCredentials(BaseModel):
    """Credentials returned to mobile app for SDK authentication"""
    userId: str
    accessToken: str
    refreshToken: Optional[str] = None


class OpenWearablesUser(BaseModel):
    """OpenWearables user response"""
    id: str
    created_at: datetime
    external_user_id: Optional[str] = None
    email: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_synced_provider: Optional[str] = None


class OpenWearablesTokenResponse(BaseModel):
    """Token response from OpenWearables API"""
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


class ConnectHealthRequest(BaseModel):
    """Optional request body for connect endpoint"""
    pass  # No required fields, user is authenticated via JWT


class ConnectionStatus(BaseModel):
    """Health data connection status"""
    connected: bool
    openWearablesUserId: Optional[str] = None
    lastSyncedAt: Optional[datetime] = None
    lastSyncedProvider: Optional[str] = None
