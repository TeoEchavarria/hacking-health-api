"""
Pydantic schemas for location domain.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# =============================================================================
# Request Schemas
# =============================================================================

class LocationUpdateRequest(BaseModel):
    """Request to update user's current location."""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in degrees")
    accuracy: Optional[float] = Field(None, ge=0, description="Location accuracy in meters")
    timestamp: Optional[int] = Field(None, description="Client timestamp in milliseconds")


class SharingToggleRequest(BaseModel):
    """Request to toggle location sharing preference."""
    sharing_enabled: bool = Field(..., alias="sharingEnabled", description="Whether to share location with paired user")
    
    class Config:
        populate_by_name = True


# =============================================================================
# Response Schemas
# =============================================================================

class LocationUpdateResponse(BaseModel):
    """Response after updating location."""
    success: bool
    updated_at: int = Field(..., alias="updatedAt", description="Server timestamp in milliseconds")
    
    class Config:
        populate_by_name = True


class LocationResponse(BaseModel):
    """Response containing a user's location."""
    user_id: str = Field(..., alias="userId")
    user_name: str = Field(..., alias="userName")
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    updated_at: int = Field(..., alias="updatedAt", description="Timestamp in milliseconds")
    
    class Config:
        populate_by_name = True


class PairedLocationResponse(BaseModel):
    """Response containing paired user's location."""
    found: bool
    location: Optional[LocationResponse] = None
    message: Optional[str] = None


# =============================================================================
# New Response Schemas for self + partner locations
# =============================================================================

class LocationCoordinates(BaseModel):
    """GPS coordinates with accuracy."""
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    updated_at: Optional[int] = Field(None, alias="updatedAt", description="Timestamp in milliseconds")
    
    class Config:
        populate_by_name = True


class UserLocationInfo(BaseModel):
    """User location info for map display."""
    name: str
    avatar: Optional[str] = None
    role: str = Field(..., description="'patient' or 'caregiver'")
    location: Optional[LocationCoordinates] = None
    sharing_enabled: bool = Field(True, alias="sharingEnabled")
    
    class Config:
        populate_by_name = True


class PartnerLocationInfo(BaseModel):
    """Partner location info with stale detection."""
    name: str
    avatar: Optional[str] = None
    role: str = Field(..., description="'patient' or 'caregiver'")
    location: Optional[LocationCoordinates] = None
    location_stale: bool = Field(False, alias="locationStale", description="True if location is older than 15 minutes")
    last_seen_at: Optional[int] = Field(None, alias="lastSeenAt", description="Last location update timestamp in ms")
    sharing_enabled: bool = Field(True, alias="sharingEnabled")
    sharing_disabled_message: Optional[str] = Field(None, alias="sharingDisabledMessage")
    
    class Config:
        populate_by_name = True


class RelationLocationsResponse(BaseModel):
    """
    Response containing both self and partner location info.
    
    This is the new response format for GET /api/location/paired that includes:
    - self: Current user's name, avatar, role, and location
    - partner: Paired user's info with locationStale flag
    - hasRelation: Whether an active pairing exists
    - message: Optional explanation message
    """
    self_info: Optional[UserLocationInfo] = Field(None, alias="self")
    partner: Optional[PartnerLocationInfo] = None
    has_relation: bool = Field(False, alias="hasRelation")
    message: Optional[str] = None
    
    class Config:
        populate_by_name = True


class SharingStatusResponse(BaseModel):
    """Response for sharing status."""
    sharing_enabled: bool = Field(..., alias="sharingEnabled")
    
    class Config:
        populate_by_name = True


class LocationHistoryResponse(BaseModel):
    """Response containing location history."""
    user_id: str = Field(..., alias="userId")
    locations: list[LocationResponse]
    
    class Config:
        populate_by_name = True
