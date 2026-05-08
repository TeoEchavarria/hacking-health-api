from fastapi import APIRouter, HTTPException, Body, Depends, Query, Header, BackgroundTasks, File, UploadFile
from fastapi.responses import JSONResponse
from src.domains.health.schemas import (
    SensorBatch, SensorBatchDB, 
    PatientDataResponse, PatientAlertsResponse,
    PatientHealthSummaryResponse,
    HealthMetricsInput, HealthMetricsResponse,
    SyncRequestCreate, SyncRequestResponse, PendingSyncResponse,
    SyncCompleteInput, SyncCompleteResponse,
    HeartRateHistoryResponse,
    BloodPressureSubmission, BloodPressureResponse,
    BloodPressureBatchInput, BloodPressureBatchResponse,
    BloodPressureHistoryResponse,
    VoiceParseRequest, VoiceParseResult, AudioParseResult,
    BiometricsHistoryResponse
)
from src.domains.health.services import HealthService
from src.domains.health.classification import classify_blood_pressure, detect_crisis
from src.domains.health.pipeline import BloodPressurePipeline
from src.domains.health.alert_generator import AlertGenerator
from src.domains.health.voice_parsing import get_voice_parsing_service
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
    - Heart rate (avg, min, max, last reading, category)
    - Blood pressure (avg, min, max, last reading, stage)
    - Steps (total)
    - Sleep (total minutes)
    
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


# =========================================
# Blood Pressure Endpoints
# =========================================

@router.post("/blood-pressure", response_model=BloodPressureResponse)
async def upload_blood_pressure(
    reading: BloodPressureSubmission,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Upload a single blood pressure reading.
    
    Performs synchronous crisis detection before returning, then runs
    the full analysis pipeline (rolling stats, anomaly detection, 
    trend analysis) as a background task.
    
    If crisis_flag is True, the edge device already detected and
    displayed a crisis alert to the user.
    """
    try:
        # Verify user is uploading their own data
        if reading.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Solo puedes subir tus propios datos de presión arterial"
            )
        
        service = HealthService(db)
        
        # Store the reading (Step 1 - synchronous)
        stored = await service.store_blood_pressure_reading(
            user_id=reading.user_id,
            systolic=reading.systolic,
            diastolic=reading.diastolic,
            pulse=reading.pulse,
            timestamp=reading.timestamp,
            source=reading.source,
            crisis_flag=reading.crisis_flag
        )
        
        # Classify the reading
        classification = classify_blood_pressure(reading.systolic, reading.diastolic)
        
        # Check for crisis (generate alert if not already flagged by edge)
        alert_generated = False
        if classification["stage"] == "hypertensive_crisis" and not reading.crisis_flag:
            alert_gen = AlertGenerator(db)
            alert = await alert_gen.generate_bp_crisis_alert(
                user_id=reading.user_id,
                systolic=reading.systolic,
                diastolic=reading.diastolic
            )
            alert_generated = alert is not None
        
        # Run analysis pipeline in background (Steps 2-6)
        pipeline = BloodPressurePipeline(db)
        background_tasks.add_task(
            pipeline.run_full_pipeline,
            user_id=reading.user_id,
            reading=stored
        )
        
        return {
            "success": True,
            "stage": classification["stage"],
            "severity": classification["severity"],
            "alert_generated": alert_generated,
            "message": "Lectura de presión arterial guardada"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading blood pressure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/blood-pressure/batch", response_model=BloodPressureBatchResponse)
async def upload_blood_pressure_batch(
    batch: BloodPressureBatchInput,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Upload multiple blood pressure readings.
    
    Stores all readings, then runs the analysis pipeline only on
    the most recent reading (to avoid alert spam).
    
    Used when syncing multiple stored readings from a device.
    """
    try:
        # Verify user is uploading their own data
        if batch.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Solo puedes subir tus propios datos de presión arterial"
            )
        
        service = HealthService(db)
        
        # Prepare readings as dicts
        readings_list = [
            {
                "systolic": r.systolic,
                "diastolic": r.diastolic,
                "pulse": r.pulse,
                "timestamp": r.timestamp,
                "source": r.source
            }
            for r in batch.readings
        ]
        
        # Store all readings
        result = await service.store_blood_pressure_batch(
            user_id=batch.user_id,
            readings=readings_list
        )
        
        # Run pipeline on most recent reading only
        alerts_generated = 0
        if result["documents"]:
            # Sort by timestamp to get most recent
            sorted_docs = sorted(
                result["documents"],
                key=lambda d: d["timestamp"],
                reverse=True
            )
            most_recent = sorted_docs[0]
            
            # Check for crisis in most recent
            classification = classify_blood_pressure(
                most_recent["systolic"], most_recent["diastolic"]
            )
            
            if classification["stage"] == "hypertensive_crisis":
                alert_gen = AlertGenerator(db)
                alert = await alert_gen.generate_bp_crisis_alert(
                    user_id=batch.user_id,
                    systolic=most_recent["systolic"],
                    diastolic=most_recent["diastolic"]
                )
                if alert:
                    alerts_generated += 1
            
            # Run pipeline in background
            pipeline = BloodPressurePipeline(db)
            background_tasks.add_task(
                pipeline.run_full_pipeline,
                user_id=batch.user_id,
                reading=most_recent
            )
        
        return {
            "success": True,
            "readings_stored": result["stored_count"],
            "alerts_generated": alerts_generated,
            "message": f"Se guardaron {result['stored_count']} lecturas"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading blood pressure batch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patient/{patient_id}/blood-pressure-history", response_model=BloodPressureHistoryResponse)
async def get_patient_blood_pressure_history(
    patient_id: str,
    days: int = Query(30, ge=1, le=90, description="Number of days of history (1-90)"),
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get blood pressure history for a patient.
    
    Returns daily aggregated blood pressure data (avg, min, max, 
    dominant stage, sample count).
    
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
        result = await service.get_patient_blood_pressure_history(
            patient_id=patient_id,
            days=days
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching blood pressure history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================================
# Voice BP Parsing Endpoint
# =========================================

@router.post("/parse-bp-voice", response_model=VoiceParseResult)
async def parse_bp_voice(
    request: VoiceParseRequest,
    user_id: str = Depends(verify_token_jwt)
):
    """
    Parse a voice transcription to extract blood pressure values.
    
    Uses LLM (OpenAI) to extract BP values from natural language,
    with regex fallback for common patterns like "120/80".
    
    Returns extracted values with a confidence level:
    - "high": Both systolic and diastolic clearly detected
    - "low": Ambiguous or incomplete values
    """
    try:
        logger.info(f"Parsing BP voice transcription for user {user_id}: {request.transcription[:100]}...")
        
        service = get_voice_parsing_service()
        result = await service.parse_transcription(request.transcription)
        
        logger.info(f"Parse result: S={result.get('systolic')} D={result.get('diastolic')} conf={result.get('confidence')}")
        
        return VoiceParseResult(
            systolic=result.get("systolic"),
            diastolic=result.get("diastolic"),
            pulse=result.get("pulse"),
            device_classification=result.get("device_classification"),
            confidence=result.get("confidence", "low")
        )
        
    except Exception as e:
        logger.error(f"Error parsing BP voice: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================================
# Audio BP Parsing Endpoint (Whisper STT)
# =========================================

@router.post("/parse-bp-audio", response_model=AudioParseResult)
async def parse_bp_audio(
    audio: UploadFile = File(...),
    user_id: str = Depends(verify_token_jwt)
):
    """
    Parse an audio recording to extract blood pressure values.
    
    Flow:
    1. Accepts audio file (3GP, AAC, M4A, MP3, WAV, WEBM)
    2. Transcribes using OpenAI Whisper (Spanish)
    3. Extracts BP values using LLM
    4. Returns values + transcription for confirmation
    
    File limits:
    - Max size: 10MB
    - Max duration: ~30 seconds recommended
    """
    try:
        logger.info(f"Received audio upload from user {user_id}: {audio.filename}, type: {audio.content_type}")
        
        # Read audio content
        audio_content = await audio.read()
        
        # Validate file size
        if len(audio_content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=413, detail="Audio file too large (max 10MB)")
        
        if len(audio_content) < 1000:  # Minimum ~1KB
            raise HTTPException(status_code=400, detail="Audio file too small or empty")
        
        logger.info(f"Audio file size: {len(audio_content)} bytes")
        
        # Parse audio (transcribe + extract BP)
        service = get_voice_parsing_service()
        result = await service.parse_audio(audio_content, audio.filename or "recording.3gp")
        
        logger.info(
            f"Audio parse result: S={result.get('systolic')} D={result.get('diastolic')} "
            f"P={result.get('pulse')} conf={result.get('confidence')}"
        )
        
        return AudioParseResult(
            systolic=result.get("systolic"),
            diastolic=result.get("diastolic"),
            pulse=result.get("pulse"),
            device_classification=result.get("device_classification"),
            confidence=result.get("confidence", "low"),
            transcription=result.get("transcription", "")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parsing BP audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================================
# Biometrics History Endpoint (Unified GET)
# =========================================

@router.get("/biometrics/{user_id}", response_model=BiometricsHistoryResponse)
async def get_user_biometrics(
    user_id: str,
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    days: int = Query(30, ge=1, le=90, description="Days of history"),
    auth_user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get biometric history for a user.
    
    Returns records ordered by timestamp DESC.
    Returns [] with status 200 for new users (NOT 404).
    
    Use this to:
    - Detect if user is new (isEmpty=true) vs has historical data
    - Get latest values for each metric type
    - Get paginated history for charts/lists
    """
    try:
        service = HealthService(db)
        
        # Authorization check
        has_access = await service.verify_patient_access(
            requester_id=auth_user_id,
            patient_id=user_id
        )
        
        if not has_access:
            raise HTTPException(
                status_code=403, 
                detail="No tienes permiso para ver estos datos"
            )
        
        # Fetch biometric data
        result = await service.get_biometrics_history(
            user_id=user_id,
            limit=limit,
            days=days
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching biometrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
