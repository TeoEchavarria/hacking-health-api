from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
from enum import Enum

class AppointmentStatus(str, Enum):
    """Estado de la cita"""
    AVAILABLE = "available"
    BOOKED = "booked"
    CANCELLED = "cancelled"

class AppointmentSlot(BaseModel):
    """Slot individual de cita"""
    slot_id: str  # Formato: "YYYY-MM-DD-HH-MM" (ej: "2024-01-15-09-00")
    date: str  # YYYY-MM-DD
    time: str  # HH:MM formato 24h
    datetime: datetime
    status: AppointmentStatus = AppointmentStatus.AVAILABLE
    booked_by: Optional[str] = None  # Nombre de la persona que reservó
    version: int = 0  # Para optimistic locking / conflict resolution

class AppointmentCreate(BaseModel):
    """Request para crear/reservar una cita"""
    slot_id: str
    name: str = Field(..., min_length=1, description="Nombre de la persona que reserva")
    
    @validator("name")
    def validate_name(cls, v: str) -> str:
        return v.strip()

class AppointmentCancel(BaseModel):
    """Request para cancelar una cita"""
    slot_id: str
    name: str = Field(..., description="Nombre de la persona que canceló la reserva")

class AppointmentBookRange(BaseModel):
    """Request para reservar una cita según disponibilidad en un día y rango horario."""
    date: str = Field(..., description="Día de la cita (YYYY-MM-DD)")
    start_time: str = Field(..., description="Inicio del rango (HH:MM 24h)")
    end_time: str = Field(..., description="Fin del rango (HH:MM 24h)")
    name: str = Field(..., min_length=1, description="Nombre de la persona que reserva")

    @validator("name")
    def validate_name(cls, v: str) -> str:
        return v.strip()

class AppointmentResponse(BaseModel):
    """Response de una cita"""
    slot_id: str
    date: str
    time: str
    datetime: datetime
    status: AppointmentStatus
    booked_by: Optional[str] = None
    version: int

class WeekScheduleResponse(BaseModel):
    """Response con el horario semanal"""
    week_start: str  # Fecha de inicio de semana (Lunes)
    week_end: str  # Fecha de fin de semana (Domingo)
    slots: list[AppointmentResponse]
