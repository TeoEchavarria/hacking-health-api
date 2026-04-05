from fastapi import APIRouter, HTTPException, Body, Depends, Query, Header
from fastapi.responses import JSONResponse
from src.domains.health.schemas import (
    SensorBatch, SensorBatchDB, 
    PatientDataResponse, PatientAlertsResponse,
    PatientHealthSummaryResponse
)
from src.domains.health.services import HealthService
from src.domains.auth.routes import verify_token_jwt
from src._config.logger import get_logger
from src.core.database import get_database
from typing import Dict, Optional

logger = get_logger(__name__)

router = APIRouter(
    prefix="/health",
    tags=["health"]
)

@router.post("/sensor-data")
async def upload_sensor_data(
    batch: SensorBatch = Body(...), 
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Upload a batch of sensor data records.
    AUTHENTICATED ENDPOINT - Requires valid JWT Bearer token.
    MongoDB stores **one document per batch**, not per-sample.
    """
    try:
        # Extra guard, though pydantic handles min_items
        if not batch.records:
            return {"status": "success", "count": 0}

        logger.info(
            f"Received batch with {len(batch.records)} records from user {user_id}. "
            f"ts_range=[{batch.records[0].timestamp}..{batch.records[-1].timestamp}]"
        )
        
        # Build DB document with authenticated user's ID
        db_doc = SensorBatchDB(
            userId=user_id,
            records=batch.records
        )
            
        # Insert into SINGLE sensor_batches collection
        # One document per batch
        result = await db.sensor_batches.insert_one(db_doc.model_dump())
        
        logger.info(
            f"Inserted batch document {result.inserted_id} "
            f"for user {user_id} with {len(batch.records)} records"
        )
        
        return {
            "status": "success", 
            "batchId": str(result.inserted_id),
            "count": len(batch.records)
        }
    except Exception as e:
        logger.error(f"Error processing sensor data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patient/{patient_id}/data", response_model=PatientDataResponse)
async def get_patient_data(
    patient_id: str,
    start_time: Optional[int] = Query(None, description="Start timestamp in ms (inclusive)"),
    end_time: Optional[int] = Query(None, description="End timestamp in ms (inclusive)"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get sensor data for a patient.
    
    AUTHORIZATION:
    - If user_id == patient_id: User accessing own data
    - Otherwise: Must have active pairing as caregiver
    """
    try:
        service = HealthService(db)
        
        # Authorization check
        has_access = await service.verify_patient_access(
            requester_id=user_id,
            patient_id=patient_id
        )
        
        if not has_access:
            raise HTTPException(
                status_code=403, 
                detail="No tienes permiso para ver los datos de este paciente"
            )
        
        # Fetch data
        data = await service.get_patient_sensor_data(
            patient_id=patient_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching patient data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patient/{patient_id}/alerts", response_model=PatientAlertsResponse)
async def get_patient_alerts(
    patient_id: str,
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(50, ge=1, le=100, description="Max alerts to return"),
    severity: Optional[str] = Query(None, description="Filter by severity: info|moderate|high|urgent"),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get alerts for a patient.
    
    AUTHORIZATION:
    - If user_id == patient_id: User accessing own alerts
    - Otherwise: Must have active pairing as caregiver
    """
    try:
        service = HealthService(db)
        
        # Authorization check
        has_access = await service.verify_patient_access(
            requester_id=user_id,
            patient_id=patient_id
        )
        
        if not has_access:
            raise HTTPException(
                status_code=403, 
                detail="No tienes permiso para ver las alertas de este paciente"
            )
        
        # Fetch alerts
        alerts = await service.get_patient_alerts(
            patient_id=patient_id,
            cursor=cursor,
            limit=limit,
            severity=severity
        )
        
        return alerts
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching patient alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patient/{patient_id}/summary", response_model=PatientHealthSummaryResponse)
async def get_patient_health_summary(
    patient_id: str,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get health summary for a patient (last 24 hours).
    
    Includes:
    - Heart rate (avg, min, max, last reading)
    - Steps (total)
    - Sleep (total minutes)
    - Unavailable metrics (SpO2, Blood Pressure, Temperature)
    
    AUTHORIZATION:
    - If user_id == patient_id: User accessing own summary
    - Otherwise: Must have active pairing as caregiver
    """
    try:
        service = HealthService(db)
        
        # Authorization check
        has_access = await service.verify_patient_access(
            requester_id=user_id,
            patient_id=patient_id
        )
        
        if not has_access:
            raise HTTPException(
                status_code=403, 
                detail="No tienes permiso para ver el resumen de este paciente"
            )
        
        # Fetch summary
        summary = await service.get_patient_health_summary(patient_id=patient_id)
        
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching patient summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
