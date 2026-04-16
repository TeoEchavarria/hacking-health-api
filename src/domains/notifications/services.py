"""
Servicios para gestión de notificaciones
"""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from src.domains.notifications.models import NotificationDB, HealthTipDB, NotificationType, NotificationPriority
from src._config.logger import get_logger

logger = get_logger(__name__)

PAIRINGS_COLLECTION = "pairings"


class NotificationService:
    """Servicio para gestión de notificaciones"""
    
    def __init__(self, db):
        self.db = db
        self.notifications = db.notifications
        self.health_tips = db.health_tips
    
    async def verify_patient_access(
        self,
        db,
        requester_id: str,
        patient_id: str
    ) -> bool:
        """
        Verifica si el solicitante tiene acceso a los datos del paciente.
        
        Acceso permitido si:
        1. requester_id == patient_id (accede a sus propios datos)
        2. requester es un cuidador activo de este paciente
        """
        # Caso 1: Usuario accediendo a sus propios datos
        if requester_id == patient_id:
            return True
        
        # Caso 2: Verificar si es un cuidador activo
        pairing = await db[PAIRINGS_COLLECTION].find_one({
            "caregiverId": requester_id,
            "patientId": patient_id,
            "status": "active"
        })
        
        if pairing:
            logger.debug(
                f"Caregiver {requester_id} has active pairing with patient {patient_id}"
            )
            return True
        
        logger.warning(
            f"Access denied: User {requester_id} attempted to access "
            f"notifications of patient {patient_id} without valid pairing"
        )
        return False
    
    # =====================
    # NOTIFICATIONS
    # =====================
    
    async def create_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata: Optional[dict] = None,
        timestamp: Optional[datetime] = None
    ) -> dict:
        """Crear una nueva notificación"""
        notification_id = str(uuid4())
        
        document = NotificationDB.create_document(
            notification_id=notification_id,
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            metadata=metadata,
            timestamp=timestamp
        )
        
        await self.notifications.insert_one(document)
        logger.info(f"Created notification {notification_id} for user {user_id}")
        
        return NotificationDB.to_response(document)
    
    async def get_notifications(
        self,
        user_id: str,
        notification_type: Optional[NotificationType] = None,
        include_read: bool = True,
        limit: int = 50
    ) -> List[dict]:
        """Obtener notificaciones de un usuario"""
        query = {"userId": user_id}
        
        if notification_type:
            query["type"] = notification_type.value
        
        if not include_read:
            query["isRead"] = False
        
        cursor = self.notifications.find(query).sort("timestamp", -1).limit(limit)
        notifications = await cursor.to_list(length=limit)
        
        return [NotificationDB.to_response(n) for n in notifications]
    
    async def mark_notification_read(self, notification_id: str) -> bool:
        """Marcar una notificación como leída"""
        result = await self.notifications.update_one(
            {"_id": notification_id},
            {
                "$set": {
                    "isRead": True,
                    "updatedAt": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    async def mark_all_notifications_read(self, user_id: str) -> int:
        """Marcar todas las notificaciones de un usuario como leídas"""
        result = await self.notifications.update_many(
            {"userId": user_id, "isRead": False},
            {
                "$set": {
                    "isRead": True,
                    "updatedAt": datetime.utcnow()
                }
            }
        )
        return result.modified_count
    
    async def delete_notification(self, notification_id: str) -> bool:
        """Eliminar una notificación"""
        result = await self.notifications.delete_one({"_id": notification_id})
        return result.deleted_count > 0
    
    async def get_unread_count(self, user_id: str) -> int:
        """Obtener el número de notificaciones no leídas"""
        return await self.notifications.count_documents({
            "userId": user_id,
            "isRead": False
        })
    
    # =====================
    # HEALTH TIPS
    # =====================
    
    async def create_health_tip(
        self,
        user_id: str,
        category: str,
        title: str,
        content: str,
        source: Optional[str] = None
    ) -> dict:
        """Crear un nuevo consejo de salud"""
        tip_id = str(uuid4())
        
        document = HealthTipDB.create_document(
            tip_id=tip_id,
            user_id=user_id,
            category=category,
            title=title,
            content=content,
            source=source
        )
        
        await self.health_tips.insert_one(document)
        logger.info(f"Created health tip {tip_id} for user {user_id}")
        
        return HealthTipDB.to_response(document)
    
    async def get_health_tips(
        self,
        user_id: str,
        category: Optional[str] = None,
        limit: int = 10
    ) -> List[dict]:
        """Obtener consejos de salud de un usuario"""
        query = {"userId": user_id, "isActive": True}
        
        if category:
            query["category"] = category
        
        cursor = self.health_tips.find(query).sort("createdAt", -1).limit(limit)
        tips = await cursor.to_list(length=limit)
        
        return [HealthTipDB.to_response(t) for t in tips]
    
    async def get_random_health_tip(self, user_id: str, category: Optional[str] = None) -> Optional[dict]:
        """Obtener un consejo de salud aleatorio"""
        pipeline = [
            {"$match": {"userId": user_id, "isActive": True}},
        ]
        
        if category:
            pipeline[0]["$match"]["category"] = category
        
        pipeline.append({"$sample": {"size": 1}})
        
        cursor = self.health_tips.aggregate(pipeline)
        tips = await cursor.to_list(length=1)
        
        if tips:
            return HealthTipDB.to_response(tips[0])
        return None
