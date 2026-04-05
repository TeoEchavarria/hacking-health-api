from pydantic import BaseModel
from typing import Optional, List


class OAuthProviderInfo(BaseModel):
    """OAuth provider linked to user account"""
    provider: str
    provider_email: str
    linked_at: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    email_verified: bool = False
    name: Optional[str] = None
    profile_picture: Optional[str] = None
    oauth_providers: List[OAuthProviderInfo] = []
    created_at: str
    updated_at: str


class ConnectionInfo(BaseModel):
    """Information about a caregiver/patient connection"""
    user_id: str
    name: str
    role: str  # "caregiver" or "patient" - what this person is to the current user
    profile_picture: Optional[str] = None


class FullUserProfileResponse(BaseModel):
    """Complete user profile with role and connections"""
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    profile_picture: Optional[str] = None
    role: str  # "caregiver", "patient", or "none"
    connections: List[ConnectionInfo] = []
    created_at: str
    updated_at: str

