"""
Modelos de datos para medicamentos en MongoDB
"""
from datetime import datetime
from typing import Optional

class MedicationDB:
    """Modelo de documento MongoDB para medicamentos"""
    
    @staticmethod
    def create_document(
        medication_id: str,
        user_id: str,
        name: str,
        dosage: str,
        time: str,
        instructions: str,
        medication_type: str,  # "pill" or "injection"
        is_active: bool = True
    ) -> dict:
        """Crea un documento de medicamento para MongoDB"""
        return {
            "_id": medication_id,
            "userId": user_id,
            "name": name,
            "dosage": dosage,
            "time": time,
            "instructions": instructions,
            "medicationType": medication_type,
            "isActive": is_active,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
    
    @staticmethod
    def to_response(doc: dict) -> dict:
        """Convierte documento MongoDB a formato de respuesta"""
        return {
            "id": doc["_id"],
            "userId": doc["userId"],
            "name": doc["name"],
            "dosage": doc.get("dosage", ""),
            "time": doc["time"],
            "instructions": doc.get("instructions", ""),
            "medicationType": doc["medicationType"],
            "isActive": doc.get("isActive", True),
            "createdAt": doc.get("createdAt"),
            "updatedAt": doc.get("updatedAt")
        }


class MedicationTakeDB:
    """Modelo de documento MongoDB para registro de toma de medicamentos"""
    
    @staticmethod
    def create_document(
        take_id: str,
        medication_id: str,
        user_id: str,
        taken_at: datetime,
        date: str,  # YYYY-MM-DD for easy querying
        notes: Optional[str] = None
    ) -> dict:
        """Crea un documento de toma de medicamento para MongoDB"""
        return {
            "_id": take_id,
            "medicationId": medication_id,
            "userId": user_id,
            "takenAt": taken_at,
            "date": date,
            "notes": notes,
            "createdAt": datetime.utcnow()
        }
    
    @staticmethod
    def to_response(doc: dict) -> dict:
        """Convierte documento MongoDB a formato de respuesta"""
        return {
            "id": doc["_id"],
            "medicationId": doc["medicationId"],
            "userId": doc["userId"],
            "takenAt": doc["takenAt"],
            "date": doc["date"],
            "notes": doc.get("notes"),
            "createdAt": doc.get("createdAt")
        }
