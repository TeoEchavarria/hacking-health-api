"""
Modelos de datos para notificaciones en MongoDB
"""
from datetime import datetime
from typing import Optional, List
from enum import Enum


class NotificationType(str, Enum):
    """Tipos de notificación compatibles con Android NotificationType"""
    MEDICATION = "MEDICATION"       # 💊 Recordatorios de medicación
    ACHIEVEMENT = "ACHIEVEMENT"     # ✓ Logros de objetivos
    WARNING = "WARNING"             # ⚠ Advertencias (ej: batería baja)
    APPOINTMENT = "APPOINTMENT"     # 📅 Citas médicas
    REPORT = "REPORT"               # 📄 Reportes de salud
    HEALTH_TIP = "HEALTH_TIP"       # 💡 Consejos de salud
    VITALS = "VITALS"               # ❤️ Ventana de vitales


class NotificationPriority(str, Enum):
    """Prioridad de notificación compatible con Android NotificationPriority"""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class NotificationDB:
    """Modelo de documento MongoDB para notificaciones"""
    
    @staticmethod
    def create_document(
        notification_id: str,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        is_read: bool = False,
        metadata: Optional[dict] = None,
        timestamp: Optional[datetime] = None
    ) -> dict:
        """Crea un documento de notificación para MongoDB"""
        now = datetime.utcnow()
        return {
            "_id": notification_id,
            "userId": user_id,
            "type": notification_type.value,
            "title": title,
            "message": message,
            "priority": priority.value,
            "isRead": is_read,
            "metadata": metadata or {},
            "timestamp": timestamp or now,
            "createdAt": now,
            "updatedAt": now
        }
    
    @staticmethod
    def to_response(doc: dict) -> dict:
        """Convierte documento MongoDB a formato de respuesta"""
        return {
            "id": doc["_id"],
            "userId": doc["userId"],
            "type": doc["type"],
            "title": doc["title"],
            "message": doc["message"],
            "priority": doc.get("priority", "NORMAL"),
            "isRead": doc.get("isRead", False),
            "metadata": doc.get("metadata", {}),
            "timestamp": doc.get("timestamp"),
            "createdAt": doc.get("createdAt"),
            "updatedAt": doc.get("updatedAt")
        }


class HealthTipDB:
    """Modelo de documento MongoDB para consejos de salud"""
    
    @staticmethod
    def create_document(
        tip_id: str,
        user_id: str,
        category: str,  # "heart", "stress", "activity", "sleep", "nutrition"
        title: str,
        content: str,
        source: Optional[str] = None,  # Fuente del consejo (ej: "American Heart Association")
        is_active: bool = True
    ) -> dict:
        """Crea un documento de consejo de salud para MongoDB"""
        now = datetime.utcnow()
        return {
            "_id": tip_id,
            "userId": user_id,
            "category": category,
            "title": title,
            "content": content,
            "source": source,
            "isActive": is_active,
            "createdAt": now,
            "updatedAt": now
        }
    
    @staticmethod
    def to_response(doc: dict) -> dict:
        """Convierte documento MongoDB a formato de respuesta"""
        return {
            "id": doc["_id"],
            "userId": doc["userId"],
            "category": doc["category"],
            "title": doc["title"],
            "content": doc["content"],
            "source": doc.get("source"),
            "isActive": doc.get("isActive", True),
            "createdAt": doc.get("createdAt"),
            "updatedAt": doc.get("updatedAt")
        }
