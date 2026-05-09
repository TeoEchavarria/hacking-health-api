"""
MongoDB document models for biometric events.
"""
from datetime import datetime
from typing import Optional, Dict, Any


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
            caregiver_id: ID of linked caregiver (may be None)
            recorded_at: When the measurement occurred (defaults to now)
            
        Returns:
            Document ready for MongoDB insertion
        """
        now = datetime.utcnow()
        return {
            "patientId": patient_id,
            "caregiverId": caregiver_id,
            "type": event_type,
            "severity": severity,
            "payload": payload,
            "message": message,
            "readByPatient": False,
            "readByCaregiver": False,
            "recordedAt": recorded_at or now,
            "createdAt": now
        }
    
    @staticmethod
    def to_response(doc: dict, patient_info: Optional[dict] = None) -> dict:
        """
        Convert MongoDB document to API response format.
        
        Args:
            doc: MongoDB document
            patient_info: Optional patient info for caregiver view
            
        Returns:
            Dict formatted for API response
        """
        recorded_at = doc.get("recordedAt")
        created_at = doc.get("createdAt")
        
        response = {
            "id": str(doc["_id"]),
            "patient_id": doc["patientId"],
            "caregiver_id": doc.get("caregiverId"),
            "type": doc["type"],
            "severity": doc.get("severity", "info"),
            "payload": doc.get("payload", {}),
            "message": doc.get("message", ""),
            "read_by_patient": doc.get("readByPatient", False),
            "read_by_caregiver": doc.get("readByCaregiver", False),
            "recorded_at": int(recorded_at.timestamp() * 1000) if recorded_at else None,
            "created_at": int(created_at.timestamp() * 1000) if created_at else None
        }
        
        # Add patient info for caregiver view
        if patient_info:
            response["patient_name"] = patient_info.get("name")
            response["patient_profile_picture"] = patient_info.get("profile_picture")
        
        return response
