"""
Schemas de Pydantic para medicamentos
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MedicationType(str, Enum):
    """Tipo de medicamento"""
    PILL = "pill"
    INJECTION = "injection"


class MedicationCreate(BaseModel):
    """Request para crear un medicamento"""
    name: str = Field(..., min_length=1, description="Nombre del medicamento")
    dosage: str = Field("", description="Dosis del medicamento")
    # Legacy single time. Optional now — callers can send `times` instead.
    time: Optional[str] = Field(None, description="Hora de la toma (HH:MM) [legacy]")
    # New: multiple reminder times per day.
    times: Optional[List[str]] = Field(
        None, description="Lista de horas (HH:MM) para varias tomas al día"
    )
    instructions: str = Field("", description="Instrucciones adicionales")
    medication_type: MedicationType = Field(MedicationType.PILL, alias="medicationType")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("times")
    @classmethod
    def clean_times(cls, v):
        if not v:
            return v
        cleaned = []
        seen = set()
        for t in v:
            t = (t or "").strip()
            if not t or t in seen or ":" not in t:
                continue
            seen.add(t)
            cleaned.append(t)
        if not cleaned:
            return None
        cleaned.sort()
        return cleaned

    @model_validator(mode="after")
    def require_time_or_times(self):
        # Derive `times` from legacy `time` if needed, and ensure at least
        # one schedule entry was provided.
        if not self.times and self.time:
            self.times = [self.time]
        if not self.times:
            raise ValueError("Debe especificar al menos una hora (time o times)")
        return self

    class Config:
        populate_by_name = True


class MedicationCreateForPatient(MedicationCreate):
    """
    Request para que un cuidador cree un medicamento para su paciente.
    Igual que MedicationCreate pero requiere patient_id en la ruta.
    """
    pass


class MedicationUpdate(BaseModel):
    """Request para actualizar un medicamento"""
    name: Optional[str] = Field(None, min_length=1)
    dosage: Optional[str] = None
    time: Optional[str] = None
    times: Optional[List[str]] = None
    instructions: Optional[str] = None
    medication_type: Optional[MedicationType] = Field(None, alias="medicationType")
    is_active: Optional[bool] = Field(None, alias="isActive")

    @field_validator("times")
    @classmethod
    def normalize_times(cls, v):
        if v is None:
            return None
        cleaned = []
        seen = set()
        for t in v:
            t = (t or "").strip()
            if not t or t in seen or ":" not in t:
                continue
            seen.add(t)
            cleaned.append(t)
        cleaned.sort()
        return cleaned

    class Config:
        populate_by_name = True


class MedicationResponse(BaseModel):
    """Respuesta de medicamento"""
    id: str
    userId: str
    name: str
    dosage: str
    # Legacy: first scheduled time. Kept for backward compatibility.
    time: str
    # New: full list of scheduled times for the day.
    times: List[str] = Field(default_factory=list)
    instructions: str
    medicationType: str
    isActive: bool
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None


class TakeMedication(BaseModel):
    """Request para registrar toma de medicamento"""
    medication_id: str = Field(..., alias="medicationId")
    notes: Optional[str] = Field(None, description="Notas adicionales sobre la toma")
    taken_at: Optional[datetime] = Field(None, alias="takenAt", description="Fecha/hora de la toma. Si no se especifica, usa el momento actual")
    scheduled_time: Optional[str] = Field(
        None,
        alias="scheduledTime",
        description="Horario programado al que corresponde esta toma (HH:MM). Permite registrar de forma independiente cada slot del día."
    )

    class Config:
        populate_by_name = True


class MedicationTakeResponse(BaseModel):
    """Respuesta de toma de medicamento"""
    id: str
    medicationId: str
    userId: str
    takenAt: datetime
    date: str
    scheduledTime: Optional[str] = None
    notes: Optional[str] = None
    createdAt: Optional[datetime] = None


class TakeMedicationItem(BaseModel):
    """Una toma individual dentro de un batch"""
    medication_id: str = Field(..., alias="medicationId")
    scheduled_time: Optional[str] = Field(
        None,
        alias="scheduledTime",
        description="Horario programado al que corresponde esta toma (HH:MM)",
    )
    notes: Optional[str] = None

    class Config:
        populate_by_name = True


class TakeMedicationBatch(BaseModel):
    """Request para registrar la toma de varios medicamentos a la vez"""
    medications: List[TakeMedicationItem] = Field(..., min_length=1)
    taken_at: Optional[datetime] = Field(
        None,
        alias="takenAt",
        description="Fecha/hora compartida de la toma. Si no se especifica, usa el momento actual",
    )
    scheduled_time: Optional[str] = Field(
        None,
        alias="scheduledTime",
        description="Slot horario común (HH:MM) cuando todos los items pertenecen al mismo horario",
    )

    class Config:
        populate_by_name = True


class TakeMedicationBatchResponse(BaseModel):
    """Respuesta de toma en batch"""
    takes: List[MedicationTakeResponse]
    count: int


class MedicationWithTakes(BaseModel):
    """Medicamento con sus tomas del día"""
    medication: MedicationResponse
    takes: List[MedicationTakeResponse]
    isTakenToday: bool


class MonthlyMedicationStats(BaseModel):
    """Estadísticas mensuales de medicamentos"""
    medicationId: str
    medicationName: str
    totalDays: int  # Días del mes
    daysTaken: int  # Días que se tomó al menos una vez
    adherencePercentage: float  # Porcentaje de adherencia
    dailyTakes: dict  # {date: count} - cantidad de tomas por día


class MonthlyReportResponse(BaseModel):
    """Respuesta del reporte mensual"""
    userId: str
    month: str  # "YYYY-MM"
    year: int
    monthName: str
    medications: List[MonthlyMedicationStats]
    overallAdherence: float  # Porcentaje de adherencia general


class CalendarEventsResponse(BaseModel):
    """Eventos del calendario basados en medicamentos"""
    date: str  # "YYYY-MM-DD"
    hasMedication: bool
    medicationsTaken: int
    totalMedications: int
