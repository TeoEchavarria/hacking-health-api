"""
Pydantic schemas for biometric events domain.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class BiometricEventType(str, Enum):
    """Types of biometric events"""
    VOICE_MEASUREMENT = "voice_measurement"
    HEART_RATE_ALERT = "heart_rate_alert"
    STEPS_SUMMARY = "steps_summary"
    SLEEP_SUMMARY = "sleep_summary"
    WATCH_MEASUREMENT = "watch_measurement"
    MANUAL_ALERT = "manual_alert"


class EventSeverity(str, Enum):
    """Severity levels for events"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# =========================================
# Response Schemas
# =========================================

class PatientInfo(BaseModel):
    """Minimal patient info for event responses"""
    id: str
    name: str
    profile_picture: Optional[str] = None


class BiometricEventResponse(BaseModel):
    """Single biometric event response"""
    id: str
    patient_id: str
    caregiver_id: Optional[str] = None
    type: BiometricEventType
    severity: EventSeverity
    payload: Dict[str, Any]
    message: str
    read_by_patient: bool
    read_by_caregiver: bool
    recorded_at: int  # Unix timestamp milliseconds
    created_at: int   # Unix timestamp milliseconds
    patient_name: Optional[str] = None  # Populated for caregiver view
    patient_profile_picture: Optional[str] = None  # Populated for caregiver view


class EventsListResponse(BaseModel):
    """Paginated list of events"""
    events: List[BiometricEventResponse]
    total: int
    page: int
    limit: int
    has_more: bool


class UnreadCountResponse(BaseModel):
    """Unread events count response"""
    count: int


# =========================================
# Request Schemas
# =========================================

class EventsQueryParams(BaseModel):
    """Query parameters for events list"""
    limit: int = Field(default=20, ge=1, le=100)
    page: int = Field(default=1, ge=1)


class MarkEventsReadRequest(BaseModel):
    """Request to mark specific events as read"""
    event_ids: List[str]
