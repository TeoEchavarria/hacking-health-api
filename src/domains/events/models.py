"""
MongoDB document models for biometric events.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List


class BiometricEventDB:
    """MongoDB document helper for biometric events"""
    
    COLLECTION_NAME = "biometric_events"
    
    @staticmethod
    def create_document(
        patient_id: str,
        event_type: str,
        payload: Dict[str, Any],
        message: str,
        severity: str = "info",
        caregiver_id: Optional[str] = None,
        caregiver_ids: Optional[List[str]] = None,
        recorded_at: Optional[datetime] = None
    ) -> dict:
        """
        Create a biometric event document for MongoDB.

        Args:
            patient_id: ID of the patient who generated the event
            event_type: Type of biometric event
            payload: Raw event data (bpm, steps, transcription, etc.)
            message: Human-readable message for UI display
            severity: Event severity (info, warning, critical)
            caregiver_id: Legacy single caregiver (kept for backward compat).
            caregiver_ids: ALL active caregivers the event should fan out to.
            recorded_at: When the measurement occurred (defaults to now)

        Returns:
            Document ready for MongoDB insertion
        """
        now = datetime.utcnow()
        ids = [c for c in (caregiver_ids or ([caregiver_id] if caregiver_id else [])) if c]
        return {
            "patientId": patient_id,
            # `caregiverId` keeps the first caregiver so events created before the
            # fan-out change keep working; `caregiverIds` is the full list.
            "caregiverId": ids[0] if ids else None,
            "caregiverIds": ids,
            "type": event_type,
            "severity": severity,
            "payload": payload,
            "message": message,
            "readByPatient": False,
            # Caregiver IDs that have read this event (per-caregiver read state).
            "readByCaregivers": [],
            "recordedAt": recorded_at or now,
            "createdAt": now
        }
    
    @staticmethod
    def to_response(
        doc: dict,
        patient_info: Optional[dict] = None,
        requesting_user_id: Optional[str] = None,
    ) -> dict:
        """
        Convert MongoDB document to API response format.

        Args:
            doc: MongoDB document
            patient_info: Optional patient info for caregiver view
            requesting_user_id: The authenticated user, used to compute
                `read_by_caregiver` per-caregiver (multi-caregiver support).

        Returns:
            Dict formatted for API response
        """
        recorded_at = doc.get("recordedAt")
        created_at = doc.get("createdAt")

        caregiver_ids = doc.get("caregiverIds")
        if caregiver_ids is None:
            legacy = doc.get("caregiverId")
            caregiver_ids = [legacy] if legacy else []

        read_by_caregivers = doc.get("readByCaregivers") or []
        read_by_caregiver = (
            requesting_user_id in read_by_caregivers if requesting_user_id else False
        ) or doc.get("readByCaregiver", False)  # back-compat with single-bool events

        response = {
            "id": str(doc["_id"]),
            "patient_id": doc["patientId"],
            "caregiver_id": doc.get("caregiverId"),
            "caregiver_ids": caregiver_ids,
            "type": doc["type"],
            "severity": doc.get("severity", "info"),
            "payload": doc.get("payload", {}),
            "message": doc.get("message", ""),
            "read_by_patient": doc.get("readByPatient", False),
            "read_by_caregiver": read_by_caregiver,
            "recorded_at": int(recorded_at.timestamp() * 1000) if recorded_at else None,
            "created_at": int(created_at.timestamp() * 1000) if created_at else None
        }
        
        # Add patient info for caregiver view
        if patient_info:
            response["patient_name"] = patient_info.get("name")
            response["patient_profile_picture"] = patient_info.get("profile_picture")
        
        return response
