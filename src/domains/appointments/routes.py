"""
Rutas para gestión de citas
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime

from src.domains.appointments.schemas import (
    AppointmentCreate,
    AppointmentCancel,
    AppointmentBookRange,
    AppointmentResponse,
    WeekScheduleResponse
)
from src.domains.appointments.services import AppointmentService
from src.core.database import get_database
from src._config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/appointments",
    tags=["appointments"]
)

@router.get("/week", response_model=WeekScheduleResponse)
async def get_week_schedule(
    week_start: Optional[str] = Query(None, description="Fecha de inicio de semana (YYYY-MM-DD). Si no se proporciona, usa la semana actual."),
    db=Depends(get_database)
):
    """
    Obtiene el horario completo de una semana.
    Incluye todos los slots entre 6 AM y 6 PM, cada 30 minutos.
    Si la semana no existe, la crea automáticamente.
    """
    try:
        service = AppointmentService(db)
        
        week_start_dt = None
        if week_start:
            try:
                week_start_dt = datetime.strptime(week_start, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Formato de fecha inválido. Use YYYY-MM-DD"
                )
        
        schedule = await service.get_week_schedule(week_start_dt)
        return schedule
    
    except Exception as e:
        logger.error(f"Error getting week schedule: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/book", response_model=AppointmentResponse)
async def book_appointment(
    appointment: AppointmentCreate,
    db=Depends(get_database)
):
    """
    Reserva una cita.
    Usa operaciones atómicas de MongoDB para evitar conflictos de concurrencia.
    Si dos personas intentan reservar el mismo slot simultáneamente, solo una tendrá éxito.
    """
    try:
        service = AppointmentService(db)
        result = await service.book_appointment(
            slot_id=appointment.slot_id,
            name=appointment.name
        )
        return result
    
    except ValueError as e:
        logger.warning(f"Booking failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error booking appointment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/book-range", response_model=AppointmentResponse)
async def book_appointment_in_range(
    appointment: AppointmentBookRange,
    db=Depends(get_database)
):
    """
    Reserva una cita para un día y rango horario, seleccionando automáticamente según disponibilidad.

    Retorna exactamente la fecha/hora asignada (slot), o un error si no hay disponibilidad.
    La selección/reserva es atómica (evita choques en concurrencia).
    """
    try:
        service = AppointmentService(db)
        result = await service.book_appointment_in_range(
            date_str=appointment.date,
            start_time_str=appointment.start_time,
            end_time_str=appointment.end_time,
            name=appointment.name,
        )
        return result

    except ValueError as e:
        msg = str(e)
        # Si no hay disponibilidad, lo tratamos como conflicto
        if "No hay disponibilidad" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        logger.error(f"Error booking appointment in range: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cancel", response_model=AppointmentResponse)
async def cancel_appointment(
    appointment: AppointmentCancel,
    db=Depends(get_database)
):
    """
    Cancela una cita reservada.
    Solo la persona que reservó la cita puede cancelarla.
    """
    try:
        service = AppointmentService(db)
        result = await service.cancel_appointment(
            slot_id=appointment.slot_id,
            name=appointment.name
        )
        return result
    
    except ValueError as e:
        logger.warning(f"Cancellation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error cancelling appointment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/slot/{slot_id}", response_model=AppointmentResponse)
async def get_appointment(
    slot_id: str,
    db=Depends(get_database)
):
    """
    Obtiene información de un slot específico.
    """
    try:
        service = AppointmentService(db)
        appointment = await service.get_appointment(slot_id)
        
        if appointment is None:
            raise HTTPException(status_code=404, detail=f"Slot {slot_id} no encontrado")
        
        return appointment
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting appointment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/initialize")
async def initialize_week(
    week_start: Optional[str] = Query(None, description="Fecha de inicio de semana (YYYY-MM-DD)"),
    db=Depends(get_database)
):
    """
    Endpoint para inicializar manualmente los slots de una semana.
    Normalmente no es necesario, ya que se inicializan automáticamente.
    """
    try:
        service = AppointmentService(db)
        
        week_start_dt = None
        if week_start:
            try:
                week_start_dt = datetime.strptime(week_start, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Formato de fecha inválido. Use YYYY-MM-DD"
                )
        
        count = await service.initialize_week_slots(week_start_dt)
        return {
            "status": "success",
            "slots_created": count,
            "message": f"Se crearon {count} slots para la semana"
        }
    
    except Exception as e:
        logger.error(f"Error initializing week: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
