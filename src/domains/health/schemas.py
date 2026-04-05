from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime


class SensorRecordInput(BaseModel):
    timestamp: int
    x: float
    y: float
    z: float

    @validator("timestamp")
    def validate_timestamp(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("timestamp must be positive")
        return v


class SensorBatch(BaseModel):
    records: List[SensorRecordInput] = Field(min_length=1)


class SensorBatchDB(BaseModel):
    userId: str
    records: List[SensorRecordInput]
    createdAt: datetime = Field(default_factory=datetime.utcnow)


# =========================================
# Patient Data Response Models (Caregiver)
# =========================================

class SensorRecordOutput(BaseModel):
    """Single sensor reading for API response."""
    timestamp: int
    x: float
    y: float
    z: float


class PatientDataResponse(BaseModel):
    """Response for GET /health/patient/{patient_id}/data"""
    patient_id: str
    records: List[SensorRecordOutput]
    count: int
    has_more: bool
    oldest_timestamp: Optional[int] = None
    newest_timestamp: Optional[int] = None


# =========================================
# Patient Alerts Response Models
# =========================================

class AlertGuidance(BaseModel):
    """Guidance information for an alert."""
    category: str  # observe|habit_adjustment|consult_professional|urgent_help
    primary_message: str
    followup_question: Optional[str] = None
    suggested_actions: Optional[List[str]] = None


class AlertItem(BaseModel):
    """Single alert for API response."""
    alert_id: str
    type: str
    severity: str  # info|moderate|high|urgent
    status: str
    created_at: int  # timestamp ms
    title: str
    body: str
    guidance: Optional[AlertGuidance] = None
    cause: Optional[str] = None


class PatientAlertsResponse(BaseModel):
    """Response for GET /health/patient/{patient_id}/alerts"""
    patient_id: str
    alerts: List[AlertItem]
    count: int
    next_cursor: Optional[str] = None
    has_more: bool
