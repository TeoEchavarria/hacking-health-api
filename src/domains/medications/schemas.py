"""
Schemas de Pydantic para medicamentos
"""
from pydantic import BaseModel, Field, validator
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
    time: str = Field(..., description="Hora de la toma (HH:MM)")
    instructions: str = Field("", description="Instrucciones adicionales")
    medication_type: MedicationType = Field(MedicationType.PILL, alias="medicationType")
    
    @validator("name")
    def validate_name(cls, v: str) -> str:
        return v.strip()
    
    class Config:
        populate_by_name = True


class MedicationUpdate(BaseModel):
    """Request para actualizar un medicamento"""
    name: Optional[str] = Field(None, min_length=1)
    dosage: Optional[str] = None
    time: Optional[str] = None
    instructions: Optional[str] = None
    medication_type: Optional[MedicationType] = Field(None, alias="medicationType")
    is_active: Optional[bool] = Field(None, alias="isActive")
    
    class Config:
        populate_by_name = True


class MedicationResponse(BaseModel):
    """Respuesta de medicamento"""
    id: str
    userId: str
    name: str
    dosage: str
    time: str
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
    
    class Config:
        populate_by_name = True


class MedicationTakeResponse(BaseModel):
    """Respuesta de toma de medicamento"""
    id: str
    medicationId: str
    userId: str
    takenAt: datetime
    date: str
    notes: Optional[str] = None
    createdAt: Optional[datetime] = None


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
