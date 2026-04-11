"""
Rutas para gestión de medicamentos y recordatorios
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime

from src.domains.medications.schemas import (
    MedicationCreateForPatient,
    MedicationCreate,
    MedicationUpdate,
    MedicationResponse,
    TakeMedication,
    MedicationTakeResponse,
    MedicationWithTakes,
    MonthlyReportResponse,
    CalendarEventsResponse
)
from src.domains.medications.services import MedicationService
from src.core.database import get_database
from src.domains.auth.routes import verify_token
from src._config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/medications",
    tags=["medications"]
)


@router.get("", response_model=List[MedicationResponse])
async def get_medications(
    include_inactive: bool = Query(False, description="Incluir medicamentos inactivos"),
    patient_id: Optional[str] = Query(None, description="ID del paciente (solo para cuidadores)"),
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Obtiene todos los medicamentos del usuario.
    Por defecto solo retorna los activos.
    
    Si se especifica patient_id, el cuidador puede ver los medicamentos de su paciente.
    """
    try:
        service = MedicationService(db)
        target_user_id = patient_id or user_id
        
        # Verificar acceso si se solicitan datos de otro usuario
        if patient_id and patient_id != user_id:
            has_access = await service.verify_patient_access(db, user_id, patient_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes permiso para ver los medicamentos de este paciente"
                )
        
        medications = await service.get_medications(
            user_id=target_user_id,
            include_inactive=include_inactive
        )
        return medications
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting medications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=MedicationResponse)
async def create_medication(
    medication: MedicationCreate,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Crea un nuevo recordatorio de medicamento.
    """
    try:
        service = MedicationService(db)
        result = await service.create_medication(
            user_id=user_id,
            name=medication.name,
            dosage=medication.dosage,
            time=medication.time,
            instructions=medication.instructions,
            medication_type=medication.medication_type.value
        )
        return result
    except Exception as e:
        logger.error(f"Error creating medication: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/patient/{patient_id}", response_model=MedicationResponse)
async def create_medication_for_patient(
    patient_id: str,
    medication: MedicationCreateForPatient,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Crea un nuevo recordatorio de medicamento para un paciente (usado por cuidadores).
    
    El cuidador debe tener un pairing activo con el paciente para poder crear medicamentos.
    """
    try:
        service = MedicationService(db)
        
        # Verificar que el cuidador tiene acceso a este paciente
        has_access = await service.verify_patient_access(db, user_id, patient_id)
        if not has_access:
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para crear medicamentos para este paciente"
            )
        
        result = await service.create_medication(
            user_id=patient_id,  # El medicamento pertenece al paciente
            name=medication.name,
            dosage=medication.dosage,
            time=medication.time,
            instructions=medication.instructions,
            medication_type=medication.medication_type.value
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating medication for patient: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{medication_id}", response_model=MedicationResponse)
async def get_medication(
    medication_id: str,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Obtiene un medicamento específico.
    """
    try:
        service = MedicationService(db)
        result = await service.get_medication(
            medication_id=medication_id,
            user_id=user_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="Medicamento no encontrado")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting medication: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{medication_id}", response_model=MedicationResponse)
async def update_medication(
    medication_id: str,
    medication: MedicationUpdate,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Actualiza un medicamento existente.
    """
    try:
        service = MedicationService(db)
        
        updates = {}
        if medication.name is not None:
            updates["name"] = medication.name
        if medication.dosage is not None:
            updates["dosage"] = medication.dosage
        if medication.time is not None:
            updates["time"] = medication.time
        if medication.instructions is not None:
            updates["instructions"] = medication.instructions
        if medication.medication_type is not None:
            updates["medication_type"] = medication.medication_type.value
        if medication.is_active is not None:
            updates["is_active"] = medication.is_active
        
        result = await service.update_medication(
            medication_id=medication_id,
            user_id=user_id,
            updates=updates
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Medicamento no encontrado")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating medication: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{medication_id}")
async def delete_medication(
    medication_id: str,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Elimina un medicamento (soft delete).
    """
    try:
        service = MedicationService(db)
        result = await service.delete_medication(
            medication_id=medication_id,
            user_id=user_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Medicamento no encontrado")
        return {"message": "Medicamento eliminado correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting medication: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/take", response_model=MedicationTakeResponse)
async def take_medication(
    take: TakeMedication,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Registra la toma de un medicamento.
    Si no se especifica fecha/hora, usa el momento actual.
    
    SOLO el dueño del medicamento puede registrar tomas (no los cuidadores).
    """
    try:
        service = MedicationService(db)
        
        # Verificar que el medicamento pertenece al usuario que llama
        medication = await service.get_medication_raw(take.medication_id)
        if not medication:
            raise HTTPException(status_code=404, detail="Medicamento no encontrado")
        
        if medication.get("userId") != user_id:
            raise HTTPException(
                status_code=403,
                detail="Solo el paciente puede marcar sus medicamentos como tomados"
            )
        
        result = await service.take_medication(
            medication_id=take.medication_id,
            user_id=user_id,
            taken_at=take.taken_at,
            notes=take.notes
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Medicamento no encontrado")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording medication take: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/untake/{medication_id}")
async def untake_medication(
    medication_id: str,
    date: str = Query(..., description="Fecha de la toma a eliminar (YYYY-MM-DD)"),
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Desmarca la toma de un medicamento de un día específico.
    
    SOLO el dueño del medicamento puede desmarcar tomas (no los cuidadores).
    """
    # Verificar que el medicamento pertenece al usuario que llama
    service = MedicationService(db)
    medication = await service.get_medication_raw(medication_id)
    if not medication:
        raise HTTPException(status_code=404, detail="Medicamento no encontrado")
    
    if medication.get("userId") != user_id:
        raise HTTPException(
            status_code=403,
            detail="Solo el paciente puede modificar el estado de sus medicamentos"
        )
    try:
        service = MedicationService(db)
        result = await service.untake_medication(
            medication_id=medication_id,
            user_id=user_id,
            date_str=date
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="No se encontró toma para eliminar")
        return {"message": "Toma eliminada correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing medication take: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today/status", response_model=List[MedicationWithTakes])
async def get_today_status(
    date: Optional[str] = Query(None, description="Fecha a consultar (YYYY-MM-DD). Por defecto hoy."),
    patient_id: Optional[str] = Query(None, description="ID del paciente (solo para cuidadores)"),
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Obtiene todos los medicamentos con su estado de toma del día.
    
    Si se especifica patient_id, el cuidador puede ver el estado del paciente.
    """
    try:
        service = MedicationService(db)
        target_user_id = patient_id or user_id
        
        # Verificar acceso si se solicitan datos de otro usuario
        if patient_id and patient_id != user_id:
            has_access = await service.verify_patient_access(db, user_id, patient_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes permiso para ver los medicamentos de este paciente"
                )
        
        result = await service.get_medications_with_today_status(
            user_id=target_user_id,
            target_date=date
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting today status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/monthly", response_model=MonthlyReportResponse)
async def get_monthly_report(
    year: int = Query(..., description="Año del reporte"),
    month: int = Query(..., ge=1, le=12, description="Mes del reporte (1-12)"),
    patient_id: Optional[str] = Query(None, description="ID del paciente (solo para cuidadores)"),
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Obtiene el reporte mensual de adherencia a medicamentos.
    Incluye estadísticas de cuántos días se tomó cada medicamento.
    
    Si se especifica patient_id, el cuidador puede ver el reporte del paciente.
    """
    try:
        service = MedicationService(db)
        target_user_id = patient_id or user_id
        
        # Verificar acceso si se solicitan datos de otro usuario
        if patient_id and patient_id != user_id:
            has_access = await service.verify_patient_access(db, user_id, patient_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes permiso para ver el reporte de este paciente"
                )
        
        result = await service.get_monthly_report(
            user_id=target_user_id,
            year=year,
            month=month
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting monthly report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar/events", response_model=List[CalendarEventsResponse])
async def get_calendar_events(
    year: int = Query(..., description="Año"),
    month: int = Query(..., ge=1, le=12, description="Mes (1-12)"),
    patient_id: Optional[str] = Query(None, description="ID del paciente (solo para cuidadores)"),
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Obtiene los eventos del calendario basados en medicamentos para un mes.
    Útil para mostrar indicadores en el calendario.
    
    Si se especifica patient_id, el cuidador puede ver el calendario del paciente.
    """
    try:
        service = MedicationService(db)
        target_user_id = patient_id or user_id
        
        # Verificar acceso si se solicitan datos de otro usuario
        if patient_id and patient_id != user_id:
            has_access = await service.verify_patient_access(db, user_id, patient_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes permiso para ver el calendario de este paciente"
                )
        
        result = await service.get_calendar_events(
            user_id=target_user_id,
            year=year,
            month=month
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting calendar events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
