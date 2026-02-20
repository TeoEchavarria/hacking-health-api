"""
Modelos de datos para las citas en MongoDB
"""
from datetime import datetime
from typing import Optional

class AppointmentSlotDB:
    """Modelo de documento MongoDB para slots de citas"""
    
    @staticmethod
    def create_document(slot_id: str, date: str, time: str, datetime_obj: datetime) -> dict:
        """Crea un documento de slot para MongoDB"""
        return {
            "_id": slot_id,  # slot_id es el ID único
            "date": date,
            "time": time,
            "datetime": datetime_obj,
            "status": "available",
            "booked_by": None,
            "version": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    
    @staticmethod
    def to_response(doc: dict) -> dict:
        """Convierte documento MongoDB a formato de respuesta"""
        return {
            "slot_id": doc["_id"],
            "date": doc["date"],
            "time": doc["time"],
            "datetime": doc["datetime"],
            "status": doc["status"],
            "booked_by": doc.get("booked_by"),
            "version": doc["version"]
        }
