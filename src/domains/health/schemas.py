from pydantic import BaseModel, Field
from pydantic import field_validator, model_validator
from typing import List, Optional, Union, Any
from datetime import datetime, timezone


class SensorRecordInput(BaseModel):
    timestamp: int
    x: float
    y: float
    z: float

    @field_validator("timestamp")
    @classmethod
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
# Blood Pressure Input Models
# =========================================

class BloodPressureReadingInput(BaseModel):
    """Single BP reading from a home monitor or wearable."""
    systolic: int  # mmHg
    diastolic: int  # mmHg
    pulse: Optional[int] = None  # BPM captured during BP measurement
    timestamp: str  # ISO 8601: "2025-04-24T10:30:00Z"
    source: Optional[str] = None  # "omron_ble" | "manual" | "healthkit" | "fhir"

    @field_validator("systolic")
    @classmethod
    def validate_systolic(cls, v: int) -> int:
        if not (60 <= v <= 300):
            raise ValueError("Systolic BP out of physiologically plausible range (60-300 mmHg)")
        return v

    @field_validator("diastolic")
    @classmethod
    def validate_diastolic(cls, v: int) -> int:
        if not (30 <= v <= 200):
            raise ValueError("Diastolic BP out of physiologically plausible range (30-200 mmHg)")
        return v

    @model_validator(mode='before')
    @classmethod
    def validate_sbp_greater_than_dbp(cls, values: Any) -> Any:
        if isinstance(values, dict):
            systolic = values.get("systolic")
            diastolic = values.get("diastolic")
            if systolic is not None and diastolic is not None:
                if diastolic >= systolic:
                    raise ValueError("Diastolic must be less than systolic")
        return values

    @field_validator("pulse")
    @classmethod
    def validate_pulse(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (20 <= v <= 300):
            raise ValueError("Pulse out of physiologically plausible range (20-300 BPM)")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_format(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValueError("Invalid timestamp format (expected ISO 8601)")
        return v


class BloodPressureSubmission(BaseModel):
    """Input for POST /health/blood-pressure - single reading submission."""
    user_id: str
    systolic: int
    diastolic: int
    pulse: Optional[int] = None
    timestamp: str  # ISO 8601
    source: Optional[str] = None
    crisis_flag: bool = False  # True if edge detected crisis

    @field_validator("systolic")
    @classmethod
    def validate_systolic(cls, v: int) -> int:
        if not (60 <= v <= 300):
            raise ValueError("Systolic BP out of physiologically plausible range (60-300 mmHg)")
        return v

    @field_validator("diastolic")
    @classmethod
    def validate_diastolic(cls, v: int) -> int:
        if not (30 <= v <= 200):
            raise ValueError("Diastolic BP out of physiologically plausible range (30-200 mmHg)")
        return v

    @model_validator(mode='before')
    @classmethod
    def validate_sbp_greater_than_dbp_submission(cls, values: Any) -> Any:
        if isinstance(values, dict):
            systolic = values.get("systolic")
            diastolic = values.get("diastolic")
            if systolic is not None and diastolic is not None:
                if diastolic >= systolic:
                    raise ValueError("Diastolic must be less than systolic")
        return values


class BloodPressureBatchInput(BaseModel):
    """Batch of BP readings - used when syncing multiple stored readings."""
    user_id: str
    readings: List[BloodPressureReadingInput] = Field(min_length=1)
    sync_timestamp: str  # ISO 8601 - when the batch was sent


class BloodPressureResponse(BaseModel):
    """Response for POST /health/blood-pressure."""
    success: bool
    stage: str  # normal|elevated|hypertension_stage_1|hypertension_stage_2|hypertensive_crisis
    severity: str  # info|moderate|high|urgent
    alert_generated: bool = False
    message: Optional[str] = None


class BloodPressureBatchResponse(BaseModel):
    """Response for POST /health/blood-pressure/batch."""
    success: bool
    readings_stored: int
    alerts_generated: int = 0
    message: Optional[str] = None


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
    """Heart rate statistics - mirrors BP summary structure."""
    available: bool = False
    average: Optional[int] = None
    min: Optional[int] = None
    max: Optional[int] = None
    last_reading: Optional[int] = None
    last_reading_time: Optional[int] = None  # Epoch milliseconds
    current_category: Optional[str] = None  # bradycardia|normal|tachycardia


class StepsSummary(BaseModel):
    """Steps statistics."""
    available: bool = False
    total: Optional[int] = None
    last_updated: Optional[int] = None  # Epoch milliseconds


class SleepSummary(BaseModel):
    """Sleep statistics."""
    available: bool = False
    total_minutes: Optional[int] = None
    last_night: Optional[int] = None  # minutes
    last_updated: Optional[int] = None  # Epoch milliseconds


class BloodPressureSummary(BaseModel):
    """Aggregated BP statistics - used in patient health summary."""
    available: bool = False
    avg_systolic: Optional[int] = None
    avg_diastolic: Optional[int] = None
    min_systolic: Optional[int] = None
    max_systolic: Optional[int] = None
    last_systolic: Optional[int] = None
    last_diastolic: Optional[int] = None
    last_pulse: Optional[int] = None
    last_reading_time: Optional[int] = None  # Epoch milliseconds
    current_stage: Optional[str] = None  # See BP stages
    reading_count: int = 0


class PatientHealthSummaryResponse(BaseModel):
    """Response for GET /health/patient/{patient_id}/summary"""
    patient_id: str
    patient_name: Optional[str] = None
    heart_rate: HeartRateSummary = HeartRateSummary()
    blood_pressure: BloodPressureSummary = BloodPressureSummary()
    steps: StepsSummary = StepsSummary()
    sleep: SleepSummary = SleepSummary()
    last_sync: Optional[int] = None  # Epoch milliseconds
    data_available: bool = False


# =========================================
# Health Metrics Input (from Watch via Phone)
# =========================================

class HeartRateReadingInput(BaseModel):
    """Single heart rate reading."""
    bpm: int
    timestamp: Union[str, int]  # ISO 8601 string or epoch milliseconds
    accuracy: Optional[str] = None  # "high" | "medium" | "low"

    @field_validator("bpm")
    @classmethod
    def validate_bpm(cls, v: int) -> int:
        if not (20 <= v <= 300):
            raise ValueError("BPM out of physiologically plausible range (20-300)")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_and_convert_timestamp(cls, v: Union[str, int]) -> str:
        """Convert epoch millis to ISO 8601, or validate existing ISO string."""
        if isinstance(v, int):
            # Convert epoch milliseconds to ISO 8601
            dt = datetime.fromtimestamp(v / 1000, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValueError("Invalid timestamp format (expected ISO 8601 or epoch millis)")
        return v


# Legacy alias for backward compatibility
HeartRateMetricInput = HeartRateReadingInput


class HealthMetricsInput(BaseModel):
    """Unified health metrics payload - POST /health/metrics."""
    user_id: str
    date: str  # YYYY-MM-DD
    steps: Optional[int] = None
    sleep_minutes: Optional[int] = None
    heart_rate_samples: Optional[List[HeartRateReadingInput]] = None
    avg_heart_rate: Optional[int] = None
    min_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    sync_timestamp: Union[str, int]  # ISO 8601 string or epoch milliseconds
    source: Optional[str] = None  # "watch" | "voice" | "manual" | any string

    @field_validator("sync_timestamp")
    @classmethod
    def validate_and_convert_sync_timestamp(cls, v: Union[str, int]) -> str:
        """Convert epoch millis to ISO 8601, or validate existing ISO string."""
        if isinstance(v, int):
            # Convert epoch milliseconds to ISO 8601
            dt = datetime.fromtimestamp(v / 1000, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValueError("Invalid timestamp format (expected ISO 8601 or epoch millis)")
        return v


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
    created_at: str  # ISO 8601


class PendingSyncResponse(BaseModel):
    """Response for checking pending sync requests."""
    has_pending: bool
    request_id: Optional[str] = None
    requested_by: Optional[str] = None
    priority: Optional[str] = None
    created_at: Optional[str] = None  # ISO 8601


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

class HeartRateHistoryPoint(BaseModel):
    """Single data point for heart rate history."""
    date: str  # YYYY-MM-DD
    avg_bpm: Optional[int] = None
    min_bpm: Optional[int] = None
    max_bpm: Optional[int] = None
    sample_count: int = 0


# Legacy alias for backward compatibility
HeartRateHistoryDataPoint = HeartRateHistoryPoint


class HeartRateHistoryResponse(BaseModel):
    """Response for GET /health/patient/{patient_id}/heart-rate-history"""
    patient_id: str
    patient_name: Optional[str] = None
    days_requested: int
    data_points: List[HeartRateHistoryPoint]
    count: int


# =========================================
# Blood Pressure History Models
# =========================================

class BloodPressureHistoryPoint(BaseModel):
    """Single day data point for BP trend chart."""
    date: str  # YYYY-MM-DD
    avg_systolic: Optional[int] = None
    avg_diastolic: Optional[int] = None
    min_systolic: Optional[int] = None
    max_systolic: Optional[int] = None
    avg_pulse: Optional[int] = None
    stage: Optional[str] = None  # dominant stage for that day
    sample_count: int = 0


class BloodPressureHistoryResponse(BaseModel):
    """Response for GET /health/patient/{patient_id}/blood-pressure-history"""
    patient_id: str
    patient_name: Optional[str] = None
    days_requested: int
    data_points: List[BloodPressureHistoryPoint]
    count: int
    patient_id: str
    patient_name: Optional[str] = None
    days_requested: int
    data_points: List[HeartRateHistoryDataPoint]
    count: int


# =========================================
# Voice BP Parsing Models
# =========================================

class VoiceParseRequest(BaseModel):
    """Request for POST /health/parse-bp-voice"""
    transcription: str = Field(..., min_length=1, max_length=1000)


class VoiceParseResult(BaseModel):
    """Response for POST /health/parse-bp-voice - LLM parsed values from voice."""
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    pulse: Optional[int] = None
    device_classification: Optional[str] = None  # "omron", "manual", etc.
    confidence: str = "low"  # "high" | "low"


class AudioParseResult(BaseModel):
    """Response for POST /health/parse-bp-audio - Parsed values from audio file."""
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    pulse: Optional[int] = None
    device_classification: Optional[str] = None
    confidence: str = "low"  # "high" | "low"
    transcription: str = ""  # The transcribed text for user verification


# =========================================
# Biometrics History Models
# =========================================

class BiometricsLatest(BaseModel):
    """Latest biometric values."""
    heartRate: Optional[int] = None
    heartRateMin: Optional[int] = None
    heartRateMax: Optional[int] = None
    steps: Optional[int] = None
    sleepMinutes: Optional[int] = None
    sleepFormatted: Optional[str] = None  # "6 horas 40 minutos"


class BiometricsHistoryRecord(BaseModel):
    """Single biometric record in history."""
    id: str
    type: str  # "heart_rate" | "steps" | "sleep"
    value: Optional[int] = None
    date: str  # YYYY-MM-DD
    timestamp: str  # ISO 8601
    source: str


class BiometricsHistoryResponse(BaseModel):
    """Response for GET /health/biometrics/{user_id}"""
    isEmpty: bool
    latest: Optional[BiometricsLatest] = None
    history: List[BiometricsHistoryRecord]
    count: int
