"""
Pydantic schemas for pairing domain.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime


# =============================================================================
# Request Schemas
# =============================================================================

class CreatePairingCodeRequest(BaseModel):
    """Request to create a new pairing code (patient side)."""
    pass  # No parameters needed, uses authenticated user_id


class ValidatePairingCodeRequest(BaseModel):
    """Request to validate a pairing code (caregiver side)."""
    code: str = Field(..., min_length=6, max_length=6, description="6-digit pairing code")
    
    @validator("code")
    def validate_code(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Code must contain only digits")
        return v


# =============================================================================
# Response Schemas
# =============================================================================

class CreatePairingCodeResponse(BaseModel):
    """Response after creating a pairing code."""
    pairing_id: str = Field(..., alias="pairingId")
    code: str
    created_at: int = Field(..., alias="createdAt")
    expires_at: int = Field(..., alias="expiresAt")
    
    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class ValidatePairingCodeResponse(BaseModel):
    """Response after validating a pairing code."""
    success: bool
    pairing_id: Optional[str] = Field(None, alias="pairingId")
    patient_id: Optional[str] = Field(None, alias="patientId")
    patient_name: Optional[str] = Field(None, alias="patientName")
    error: Optional[str] = None
    
    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class PairingStatusResponse(BaseModel):
    """Response when checking pairing status."""
    pairing_id: str = Field(..., alias="pairingId")
    status: str  # "pending", "active", "expired"
    linked: bool
    caregiver_id: Optional[str] = Field(None, alias="caregiverId")
    caregiver_name: Optional[str] = Field(None, alias="caregiverName")
    patient_id: Optional[str] = Field(None, alias="patientId")
    patient_name: Optional[str] = Field(None, alias="patientName")
    created_at: int = Field(..., alias="createdAt")
    expires_at: Optional[int] = Field(None, alias="expiresAt")
    activated_at: Optional[int] = Field(None, alias="activatedAt")
    
    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class RevokePairingResponse(BaseModel):
    """Response after revoking a pairing."""
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
