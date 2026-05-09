"""
Business logic for biometric events domain.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from bson import ObjectId
from src._config.logger import get_logger
from src.domains.events.models import BiometricEventDB
from src.domains.events.schemas import BiometricEventType, EventSeverity
from src.utils.fcm_client import send_health_alert_push

logger = get_logger(__name__)

# Collection name
COLLECTION_NAME = BiometricEventDB.COLLECTION_NAME

# Keywords that trigger warning severity in voice measurements
WARNING_KEYWORDS = ["dolor", "mareo", "caída", "ayuda", "mal", "desmayo", "sangre", "emergencia"]


def build_event_message(event_type: str, payload: Dict[str, Any]) -> str:
    """
    Build a human-readable message for the event.
    
    Args:
        event_type: Type of biometric event
        payload: Raw event data
        
    Returns:
        Human-readable message for UI display
    """
    if event_type == BiometricEventType.VOICE_MEASUREMENT.value:
        transcription = payload.get("transcription", "")
        # Truncate if too long
        if len(transcription) > 50:
            transcription = transcription[:47] + "..."
        return f"Medición de voz: \"{transcription}\""
    
    elif event_type == BiometricEventType.HEART_RATE_ALERT.value:
        bpm = payload.get("bpm") or payload.get("average") or payload.get("avg_heart_rate")
        if bpm:
            status = _get_heart_rate_status(bpm)
            return f"Frecuencia cardíaca: {bpm} bpm ({status})"
        return "Frecuencia cardíaca registrada"
    
    elif event_type == BiometricEventType.STEPS_SUMMARY.value:
        steps = payload.get("steps", 0)
        return f"Pasos registrados: {steps:,} pasos"
    
    elif event_type == BiometricEventType.SLEEP_SUMMARY.value:
        minutes = payload.get("sleep_minutes", 0)
        hours = round(minutes / 60, 1)
        return f"Horas de sueño: {hours} hrs"
    
    elif event_type == BiometricEventType.WATCH_MEASUREMENT.value:
        systolic = payload.get("systolic")
        diastolic = payload.get("diastolic")
        stage = payload.get("stage", "")
        
        # Map stage to descriptive status
        status_map = {
            "normal": "Normal ✓",
            "elevated": "Elevada ⚠️",
            "stage_1": "Hipertensión Etapa 1 ⚠️",
            "stage_2": "Hipertensión Etapa 2 🔴",
            "hypertensive_crisis": "¡Crisis Hipertensiva! 🚨"
        }
        status = status_map.get(stage, "")
        
        if systolic and diastolic:
            if status:
                return f"Presión arterial: {systolic}/{diastolic} mmHg - {status}"
            return f"Presión arterial: {systolic}/{diastolic} mmHg"
        return "Medición del reloj sincronizada"
    
    elif event_type == BiometricEventType.MANUAL_ALERT.value:
        return payload.get("message", "Alerta manual")
    
    return "Evento registrado"


def _get_heart_rate_status(bpm: int) -> str:
    """Get descriptive status for heart rate."""
    if bpm > 120:
        return "muy elevada"
    elif bpm > 100:
        return "elevada"
    elif bpm < 40:
        return "muy baja"
    elif bpm < 50:
        return "baja"
    else:
        return "normal"


def resolve_severity(event_type: str, payload: Dict[str, Any]) -> str:
    """
    Determine the severity level for an event.
    
    Args:
        event_type: Type of biometric event
        payload: Raw event data
        
    Returns:
        Severity level: 'info', 'warning', or 'critical'
    """
    if event_type == BiometricEventType.HEART_RATE_ALERT.value:
        bpm = payload.get("bpm") or payload.get("average") or payload.get("avg_heart_rate")
        if bpm:
            if bpm > 120 or bpm < 40:
                return EventSeverity.CRITICAL.value
            elif bpm > 100 or bpm < 50:
                return EventSeverity.WARNING.value
    
    elif event_type == BiometricEventType.VOICE_MEASUREMENT.value:
        transcription = payload.get("transcription", "").lower()
        # Check for warning keywords
        for keyword in WARNING_KEYWORDS:
            if keyword in transcription:
                return EventSeverity.WARNING.value
    
    elif event_type == BiometricEventType.WATCH_MEASUREMENT.value:
        # Check blood pressure classification
        stage = payload.get("stage")
        if stage == "hypertensive_crisis":
            return EventSeverity.CRITICAL.value
        elif stage in ["stage_2", "stage_1"]:
            return EventSeverity.WARNING.value
    
    elif event_type == BiometricEventType.MANUAL_ALERT.value:
        # Manual alerts can specify severity
        severity = payload.get("severity")
        if severity in [s.value for s in EventSeverity]:
            return severity
    
    return EventSeverity.INFO.value


class BiometricEventService:
    """Service for managing biometric events."""
    
    def __init__(self, db):
        self.db = db
        self.collection = db[COLLECTION_NAME]
    
    async def register_biometric_event(
        self,
        patient_id: str,
        event_type: str,
        payload: Dict[str, Any],
        recorded_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Register a biometric event and optionally notify the caregiver.
        
        This is the main entry point for creating events from measurement flows.
        
        Args:
            patient_id: ID of the patient who generated the event
            event_type: Type of biometric event
            payload: Raw event data (bpm, steps, transcription, etc.)
            recorded_at: When the measurement occurred (defaults to now)
            
        Returns:
            Created event document with _id
        """
        # 1. Find active pairing to get caregiver ID
        caregiver_id = None
        caregiver_fcm_token = None
        patient_name = None
        
        try:
            # Get patient info for notifications
            patient = await self.db.users.find_one({"_id": ObjectId(patient_id)})
            if patient:
                patient_name = patient.get("name", "Tu persona cuidada")
            
            # Find active pairing
            pairing = await self.db.pairings.find_one({
                "patientId": patient_id,
                "status": "active"
            })
            
            if pairing and pairing.get("caregiverId"):
                caregiver_id = pairing["caregiverId"]
                # Get caregiver's FCM token
                caregiver = await self.db.users.find_one({"_id": ObjectId(caregiver_id)})
                if caregiver:
                    caregiver_fcm_token = caregiver.get("fcmToken")
                    
        except Exception as e:
            logger.warning(f"Error finding pairing for patient {patient_id}: {e}")
        
        # 2. Build message and determine severity
        message = build_event_message(event_type, payload)
        severity = resolve_severity(event_type, payload)
        
        # 3. Create event document
        event_doc = BiometricEventDB.create_document(
            patient_id=patient_id,
            event_type=event_type,
            payload=payload,
            message=message,
            severity=severity,
            caregiver_id=caregiver_id,
            recorded_at=recorded_at or datetime.now(timezone.utc)
        )
        
        # 4. Insert into database
        result = await self.collection.insert_one(event_doc)
        event_doc["_id"] = result.inserted_id
        
        logger.info(
            f"Created biometric event: type={event_type}, severity={severity}, "
            f"patient={patient_id}, caregiver={caregiver_id}"
        )
        
        # 5. Send push notification to caregiver (fire-and-forget)
        if caregiver_id and caregiver_fcm_token:
            try:
                # Título según severidad
                title_map = {
                    "critical": "🚨 ALERTA CRÍTICA",
                    "warning": "⚠️ Advertencia de salud",
                    "info": "📊 Nueva medición registrada"
                }
                push_title = title_map.get(severity, "Nueva alerta de tu persona cuidada")
                
                await send_health_alert_push(
                    fcm_tokens=[caregiver_fcm_token],
                    alert_type=event_type,
                    title=push_title,
                    body=f"{patient_name}: {message}" if patient_name else message,
                    patient_id=patient_id,
                    patient_name=patient_name,
                    severity=severity,
                    is_caregiver_notification=True
                )
                logger.info(f"Push notification sent to caregiver {caregiver_id}")
            except Exception as e:
                # Don't fail event creation if push fails
                logger.error(f"Failed to send push notification: {e}")
        
        return event_doc
    
    async def get_events_for_user(
        self,
        user_id: str,
        limit: int = 20,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Get paginated events where user is either patient or caregiver.
        
        Args:
            user_id: ID of the authenticated user
            limit: Max events per page
            page: Page number (1-indexed)
            
        Returns:
            Dict with events list, total count, pagination info
        """
        skip = (page - 1) * limit
        
        # Query: user is either patient or caregiver
        query = {
            "$or": [
                {"patientId": user_id},
                {"caregiverId": user_id}
            ]
        }
        
        # Count total
        total = await self.collection.count_documents(query)
        
        # Fetch events
        cursor = self.collection.find(query).sort("recordedAt", -1).skip(skip).limit(limit)
        events_raw = await cursor.to_list(length=limit)
        
        # Determine user's role for each event and format response
        events = []
        patient_ids_to_fetch = set()
        
        # Collect patient IDs for caregiver view
        for event in events_raw:
            if event.get("caregiverId") == user_id:
                patient_ids_to_fetch.add(event["patientId"])
        
        # Fetch patient info in batch
        patient_info_map = {}
        if patient_ids_to_fetch:
            patients_cursor = self.db.users.find({
                "_id": {"$in": [ObjectId(pid) for pid in patient_ids_to_fetch]}
            })
            async for patient in patients_cursor:
                patient_info_map[str(patient["_id"])] = {
                    "name": patient.get("name"),
                    "profile_picture": patient.get("profile_picture")
                }
        
        # Format events
        for event in events_raw:
            is_caregiver_view = event.get("caregiverId") == user_id
            patient_info = patient_info_map.get(event["patientId"]) if is_caregiver_view else None
            events.append(BiometricEventDB.to_response(event, patient_info))
        
        # Mark events as read (bulk update)
        await self._mark_events_as_read(user_id, events_raw)
        
        return {
            "events": events,
            "total": total,
            "page": page,
            "limit": limit,
            "has_more": (skip + len(events)) < total
        }
    
    async def _mark_events_as_read(self, user_id: str, events: List[dict]):
        """
        Mark events as read for the user (patient or caregiver).
        
        Args:
            user_id: ID of the user reading the events
            events: List of event documents
        """
        if not events:
            return
        
        # Separate events by role
        patient_event_ids = []
        caregiver_event_ids = []
        
        for event in events:
            if event.get("patientId") == user_id and not event.get("readByPatient"):
                patient_event_ids.append(event["_id"])
            elif event.get("caregiverId") == user_id and not event.get("readByCaregiver"):
                caregiver_event_ids.append(event["_id"])
        
        # Bulk update for patient reads
        if patient_event_ids:
            await self.collection.update_many(
                {"_id": {"$in": patient_event_ids}},
                {"$set": {"readByPatient": True}}
            )
            logger.debug(f"Marked {len(patient_event_ids)} events as read by patient {user_id}")
        
        # Bulk update for caregiver reads
        if caregiver_event_ids:
            await self.collection.update_many(
                {"_id": {"$in": caregiver_event_ids}},
                {"$set": {"readByCaregiver": True}}
            )
            logger.debug(f"Marked {len(caregiver_event_ids)} events as read by caregiver {user_id}")
    
    async def get_unread_count(self, user_id: str) -> int:
        """
        Get count of unread events for the user.
        
        Args:
            user_id: ID of the authenticated user
            
        Returns:
            Number of unread events
        """
        count = await self.collection.count_documents({
            "$or": [
                {"patientId": user_id, "readByPatient": False},
                {"caregiverId": user_id, "readByCaregiver": False}
            ]
        })
        return count


# Factory function for easy import
def get_event_service(db) -> BiometricEventService:
    """Get an instance of BiometricEventService."""
    return BiometricEventService(db)
