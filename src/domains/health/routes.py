from fastapi import APIRouter, HTTPException, Body, Depends, Query, Header
from fastapi.responses import JSONResponse
from src.domains.health.schemas import (
    SensorBatch, SensorBatchDB, 
    PatientDataResponse, PatientAlertsResponse,
    PatientHealthSummaryResponse,
    HealthMetricsInput, HealthMetricsResponse,
    SyncRequestCreate, SyncRequestResponse, PendingSyncResponse,
    SyncCompleteInput, SyncCompleteResponse,
    HeartRateHistoryResponse
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


@router.post("/metrics", response_model=HealthMetricsResponse)
async def upload_health_metrics(
    metrics: HealthMetricsInput,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Upload health metrics from watch (via phone app).
    
    Called when:
    - Watch sends data to phone (immediate sync)
    - Periodic sync every 15 minutes
    
    Stores heart rate, steps, and sleep data.
    """
    try:
        # Verify user is uploading their own data
        if metrics.user_id != user_id:
            raise HTTPException(status_code=403,
                detail="Solo puedes subir tus propios datos de salud"
            )
        
        service = HealthService(db)
        result = await service.ingest_health_metrics(metrics)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading health metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================================
# Sync Request Endpoints (On-Demand Sync)
# =========================================

@router.post("/sync/request/{patient_id}", response_model=SyncRequestResponse)
async def create_sync_request(
    patient_id: str,
    request: SyncRequestCreate = Body(default=SyncRequestCreate()),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Create a sync request for a patient.
    Called by caregiver to request immediate sync from patient's device.
    
    The patient's device will poll for pending requests and sync when found.
    """
    try:
        service = HealthService(db)
        
        # Authorization: must be a caregiver for this patient
        has_access = await service.verify_patient_access(
            requester_id=user_id,
            patient_id=patient_id
        )
        
        if not has_access:
            raise HTTPException(
                status_code=403, 
                detail="No tienes permiso para solicitar sync de este paciente"
            )
        
        # Create sync request
        result = await service.create_sync_request(
            patient_id=patient_id,
            requested_by=user_id,
            priority=request.priority
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating sync request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/pending", response_model=PendingSyncResponse)
async def get_pending_sync_request(
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Check for pending sync requests for the current user.
    Called by patient's device to check if sync is needed.
    
    Returns the oldest pending request if any.
    """
    try:
        service = HealthService(db)
        result = await service.get_pending_sync_request(patient_id=user_id)
        return result
        
    except Exception as e:
        logger.error(f"Error checking pending sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/complete", response_model=SyncCompleteResponse)
async def complete_sync_request(
    request: SyncCompleteInput,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Mark a sync request as complete.
    Called by patient's device after syncing data.
    """
    try:
        service = HealthService(db)
        result = await service.complete_sync_request(
            request_id=request.request_id,
            metrics_synced=request.metrics_synced
        )
        return result
        
    except Exception as e:
        logger.error(f"Error completing sync request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================================
# Heart Rate History Endpoint
# =========================================

@router.get("/patient/{patient_id}/heart-rate-history", response_model=HeartRateHistoryResponse)
async def get_patient_heart_rate_history(
    patient_id: str,
    days: int = Query(7, ge=1, le=30, description="Number of days of history (1-30)"),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get heart rate history for a patient.
    
    Returns daily aggregated heart rate data (avg, min, max, sample count).
    
    AUTHORIZATION:
    - If user_id == patient_id: User accessing own history
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
                detail="No tienes permiso para ver el historial de este paciente"
            )
        
        # Fetch history
        result = await service.get_patient_heart_rate_history(
            patient_id=patient_id,
            days=days
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching heart rate history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
