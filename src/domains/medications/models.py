"""
Modelos de datos para medicamentos en MongoDB
"""
from datetime import datetime
from typing import Optional, List

class MedicationDB:
    """Modelo de documento MongoDB para medicamentos"""

    @staticmethod
    def create_document(
        medication_id: str,
        user_id: str,
        name: str,
        dosage: str,
        times: List[str],
        instructions: str,
        medication_type: str,  # "pill" or "injection"
        is_active: bool = True
    ) -> dict:
        """Crea un documento de medicamento para MongoDB.

        Almacena `times` (lista de horarios HH:MM) y mantiene `time`
        sincronizado con el primer horario para compatibilidad con clientes
        antiguos.
        """
        primary_time = times[0] if times else ""
        return {
            "_id": medication_id,
            "userId": user_id,
            "name": name,
            "dosage": dosage,
            "time": primary_time,
            "times": list(times),
            "instructions": instructions,
            "medicationType": medication_type,
            "isActive": is_active,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }

    @staticmethod
    def normalize_times(doc: dict) -> List[str]:
        """Obtiene la lista de horarios de un documento, con fallback al
        campo legacy `time` si `times` no existe."""
        times = doc.get("times")
        if isinstance(times, list) and times:
            return [t for t in times if t]
        legacy = doc.get("time")
        return [legacy] if legacy else []

    @staticmethod
    def to_response(doc: dict) -> dict:
        """Convierte documento MongoDB a formato de respuesta"""
        times = MedicationDB.normalize_times(doc)
        return {
            "id": doc["_id"],
            "userId": doc["userId"],
            "name": doc["name"],
            "dosage": doc.get("dosage", ""),
            "time": times[0] if times else doc.get("time", ""),
            "times": times,
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
        notes: Optional[str] = None,
        scheduled_time: Optional[str] = None,  # "HH:MM" — slot this take fulfills
    ) -> dict:
        """Crea un documento de toma de medicamento para MongoDB"""
        return {
            "_id": take_id,
            "medicationId": medication_id,
            "userId": user_id,
            "takenAt": taken_at,
            "date": date,
            "scheduledTime": scheduled_time,
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
            "scheduledTime": doc.get("scheduledTime"),
            "notes": doc.get("notes"),
            "createdAt": doc.get("createdAt")
        }
