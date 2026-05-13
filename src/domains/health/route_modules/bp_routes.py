"""
Blood Pressure Routes.

Handles:
- Single BP reading upload with crisis detection
- Batch BP upload for syncing historical data
- BP history queries with access control

Crisis detection runs synchronously, full pipeline in background.
Following Single Responsibility Principle (SRP).
"""
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from src.domains.health.schemas import (
    BloodPressureSubmission, BloodPressureResponse,
    BloodPressureBatchInput, BloodPressureBatchResponse,
    BloodPressureHistoryResponse
)
from src.domains.health.services import HealthService
from src.domains.health.classification import classify_blood_pressure
from src.domains.health.pipeline import BloodPressurePipeline
from src.domains.health.alert_generator import AlertGenerator
from src.domains.events.services import BiometricEventService
from src.domains.events.schemas import BiometricEventType
from src.domains.auth.routes import verify_token_jwt
from src._config.logger import get_logger
from src.core.database import get_database

logger = get_logger(__name__)

router = APIRouter()


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

        # Register biometric event for notifications (fire-and-forget)
        try:
            event_service = BiometricEventService(db)
            await event_service.register_biometric_event(
                patient_id=reading.user_id,
                event_type=BiometricEventType.WATCH_MEASUREMENT.value,
                payload={
                    "systolic": reading.systolic,
                    "diastolic": reading.diastolic,
                    "pulse": reading.pulse,
                    "stage": classification["stage"],
                    "severity": classification["severity"],
                    "source": reading.source
                }
            )
        except Exception as e:
            logger.warning(f"Failed to register blood pressure event: {e}")

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
