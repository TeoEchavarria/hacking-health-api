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


# =========================================
# Patient Health Summary Response Models
# =========================================

class HeartRateSummary(BaseModel):
    """Heart rate statistics."""
    available: bool = False
    average: Optional[int] = None
    min: Optional[int] = None
    max: Optional[int] = None
    last_reading: Optional[int] = None
    last_reading_time: Optional[int] = None  # timestamp ms


class StepsSummary(BaseModel):
    """Steps statistics."""
    available: bool = False
    total: Optional[int] = None
    last_updated: Optional[int] = None  # timestamp ms


class SleepSummary(BaseModel):
    """Sleep statistics."""
    available: bool = False
    total_minutes: Optional[int] = None
    last_night: Optional[int] = None  # minutes
    last_updated: Optional[int] = None  # timestamp ms


class UnavailableMetric(BaseModel):
    """Metric that is not available from device."""
    name: str
    reason: str = "NO DISPONIBLE PARA TU DISPOSITIVO"


class PatientHealthSummaryResponse(BaseModel):
    """Response for GET /health/patient/{patient_id}/summary"""
    patient_id: str
    patient_name: Optional[str] = None
    heart_rate: HeartRateSummary = HeartRateSummary()
    steps: StepsSummary = StepsSummary()
    sleep: SleepSummary = SleepSummary()
    unavailable_metrics: List[UnavailableMetric] = [
        UnavailableMetric(name="SpO2"),
        UnavailableMetric(name="Presión Arterial"),
        UnavailableMetric(name="Temperatura")
    ]
    last_sync: Optional[int] = None  # timestamp ms
    data_available: bool = False


# =========================================
# Health Metrics Input (from Watch via Phone)
# =========================================

class HeartRateMetricInput(BaseModel):
    """Single heart rate reading."""
    bpm: int
    timestamp: int  # ms
    accuracy: Optional[str] = None


class HealthMetricsInput(BaseModel):
    """Input for POST /health/metrics - receives watch health data."""
    user_id: str
    date: str  # YYYY-MM-DD
    steps: Optional[int] = None
    sleep_minutes: Optional[int] = None
    heart_rate_samples: Optional[List[HeartRateMetricInput]] = None
    avg_heart_rate: Optional[int] = None
    min_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    sync_timestamp: int  # ms


class HealthMetricsResponse(BaseModel):
    """Response for POST /health/metrics"""
    success: bool
    message: str
    metrics_stored: int = 0


# =========================================
# Sync Request Models (On-Demand Sync)
# =========================================

class SyncRequestCreate(BaseModel):
    """Input for creating a sync request."""
    priority: str = "normal"  # normal|urgent


class SyncRequestResponse(BaseModel):
    """Response for sync request creation."""
    request_id: str
    patient_id: str
    requested_by: str
    status: str
    created_at: int  # timestamp ms


class PendingSyncResponse(BaseModel):
    """Response for checking pending sync requests."""
    has_pending: bool
    request_id: Optional[str] = None
    requested_by: Optional[str] = None
    priority: Optional[str] = None
    created_at: Optional[int] = None


class SyncCompleteInput(BaseModel):
    """Input for marking a sync as complete."""
    request_id: str
    metrics_synced: int = 0


class SyncCompleteResponse(BaseModel):
    """Response for sync completion."""
    success: bool
    message: str


# =========================================
# Heart Rate History Models
# =========================================

class HeartRateHistoryDataPoint(BaseModel):
    """Single data point for heart rate history."""
    date: str  # YYYY-MM-DD
    avg_bpm: Optional[int] = None
    min_bpm: Optional[int] = None
    max_bpm: Optional[int] = None
    sample_count: int = 0


class HeartRateHistoryResponse(BaseModel):
    """Response for GET /health/patient/{patient_id}/heart-rate-history"""
    patient_id: str
    patient_name: Optional[str] = None
    days_requested: int
    data_points: List[HeartRateHistoryDataPoint]
    count: int
