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

