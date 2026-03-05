from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class DeviceRegistrationRequest(BaseModel):
    provisioning_code: str = Field(..., min_length=4, max_length=64)
    hardware_id: str = Field(..., min_length=3, max_length=128)
    device_model: str = Field(..., min_length=1, max_length=64)
    software_version: str = Field(..., min_length=1, max_length=32)
    locale: Optional[str] = Field(default=None, max_length=16)
    time_zone: Optional[str] = Field(default=None, max_length=64)


class PatientContext(BaseModel):
    patient_id: str
    age_band: Optional[str] = None
    preferred_name: Optional[str] = None


class DeviceRegistrationResponse(BaseModel):
    device_id: str
    device_secret: str
    access_token: str
    access_token_expires_in: int
    patient_context: Optional[PatientContext] = None


class DeviceTokenRequest(BaseModel):
    device_id: str
    device_secret: str
    grant_type: Literal["device_credentials"]


class DeviceTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int


Severity = Literal["info", "moderate", "high", "urgent"]


class FollowupOption(BaseModel):
    id: str
    label: str


class FollowupQuestion(BaseModel):
    question_id: str
    prompt: str
    response_type: Literal["single_choice", "free_text", "yes_no"]
    options: Optional[List[FollowupOption]] = None


class AlertGuidance(BaseModel):
    category: Literal["observe", "habit_adjustment", "consult_professional", "urgent_help"]
    primary_message: str
    followup_question: Optional[FollowupQuestion] = None
    suggested_actions: Optional[List[str]] = None


class AlertEscalation(BaseModel):
    can_escalate: bool = False
    escalation_type: Optional[str] = None
    escalation_window_seconds: Optional[int] = None


class Alert(BaseModel):
    alert_id: str
    patient_id: str
    type: str
    severity: Severity
    status: str
    created_at: datetime
    valid_until: Optional[datetime] = None
    title: str
    body: str
    guidance: AlertGuidance
    escalation: Optional[AlertEscalation] = None


class AlertsResponse(BaseModel):
    alerts: List[Alert]
    next_cursor: Optional[str]
    has_more: bool
    server_time: datetime


class AlertAckItem(BaseModel):
    alert_id: str
    status: Literal["delivered", "acted_on", "dismissed", "failed"]
    failure_reason: Optional[str] = None


class AlertAckRequest(BaseModel):
    acks: List[AlertAckItem]
    up_to_cursor: Optional[str] = None


class AlertAckResponse(BaseModel):
    accepted_alert_ids: List[str]
    duplicate: bool = False
    server_cursor: Optional[str] = None


class DeviceEvent(BaseModel):
    event_id: str
    event_type: Literal[
        "wake_word_triggered",
        "user_utterance_captured",
        "followup_answer_recorded",
        "assistant_response_played",
        "urgent_escalation_triggered",
        "playback_failure",
        "network_failure",
        "cloud_alert_processed",
        "other",
    ]
    timestamp: datetime
    alert_id: Optional[str] = None
    command_id: Optional[str] = None
    payload: Optional[dict] = None


class DeviceEventsRequest(BaseModel):
    events: List[DeviceEvent]


class DeviceEventsResponse(BaseModel):
    accepted_event_ids: List[str]
    duplicate: bool = False


NetworkStatus = Literal["online", "degraded", "offline_cached"]
MicStatus = Literal["ok", "muted", "hardware_fault"]
SpeakerStatus = Literal["ok", "hardware_fault"]


class NetworkHealth(BaseModel):
    status: NetworkStatus
    latency_ms: Optional[int] = None


class AudioHealth(BaseModel):
    mic_status: MicStatus
    speaker_status: SpeakerStatus


class StorageHealth(BaseModel):
    disk_free_mb: Optional[int] = None


class HeartbeatRequest(BaseModel):
    timestamp: datetime
    uptime_seconds: int
    software_version: str
    os_version: Optional[str] = None
    network: Optional[NetworkHealth] = None
    audio: Optional[AudioHealth] = None
    storage: Optional[StorageHealth] = None
    pending_error_code: Optional[str] = None


class HeartbeatResponse(BaseModel):
    server_time: datetime
    heartbeat_interval_hint_seconds: int = 300
    config_version: Optional[str] = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None
    correlation_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail

