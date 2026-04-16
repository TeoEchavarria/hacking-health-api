"""
Rutas para gestión de notificaciones y consejos de salud
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

from src.domains.notifications.models import NotificationType, NotificationPriority
from src.domains.notifications.services import NotificationService
from src.core.database import get_database
from src.domains.auth.routes import verify_token
from src._config.logger import get_logger
from src._config.settings import settings

logger = get_logger(__name__)

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"]
)


# =====================
# SCHEMAS
# =====================

class NotificationCreate(BaseModel):
    """Schema para crear una notificación"""
    type: NotificationType
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=1000)
    priority: NotificationPriority = NotificationPriority.NORMAL
    metadata: Optional[dict] = None


class NotificationResponse(BaseModel):
    """Schema de respuesta para notificación"""
    id: str
    userId: str
    type: str
    title: str
    message: str
    priority: str
    isRead: bool
    metadata: dict
    timestamp: Optional[datetime]
    createdAt: Optional[datetime]
    updatedAt: Optional[datetime]


class HealthTipCreate(BaseModel):
    """Schema para crear un consejo de salud"""
    category: str = Field(..., description="Categoría: heart, stress, activity, sleep, nutrition")
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=2000)
    source: Optional[str] = Field(None, max_length=200)


class HealthTipResponse(BaseModel):
    """Schema de respuesta para consejo de salud"""
    id: str
    userId: str
    category: str
    title: str
    content: str
    source: Optional[str]
    isActive: bool
    createdAt: Optional[datetime]
    updatedAt: Optional[datetime]


class UnreadCountResponse(BaseModel):
    """Schema para conteo de no leídas"""
    unreadCount: int


# =====================
# NOTIFICATION ROUTES
# =====================

@router.get("", response_model=List[NotificationResponse])
async def get_notifications(
    notification_type: Optional[NotificationType] = Query(None, description="Filtrar por tipo"),
    include_read: bool = Query(True, description="Incluir notificaciones leídas"),
    limit: int = Query(50, ge=1, le=100, description="Límite de resultados"),
    patient_id: Optional[str] = Query(None, description="ID del paciente (solo para cuidadores)"),
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Obtiene las notificaciones del usuario.
    """
    try:
        service = NotificationService(db)
        target_user_id = patient_id or user_id
        
        # Verificar acceso si se solicitan datos de otro usuario
        # En modo DEBUG, permitir acceso directo para pruebas
        if patient_id and patient_id != user_id and not settings.DEBUG:
            has_access = await service.verify_patient_access(db, user_id, patient_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes permiso para ver las notificaciones de este paciente"
                )
        
        notifications = await service.get_notifications(
            user_id=target_user_id,
            notification_type=notification_type,
            include_read=include_read,
            limit=limit
        )
        return notifications
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notifications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=NotificationResponse)
async def create_notification(
    notification: NotificationCreate,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Crea una nueva notificación.
    """
    try:
        service = NotificationService(db)
        result = await service.create_notification(
            user_id=user_id,
            notification_type=notification.type,
            title=notification.title,
            message=notification.message,
            priority=notification.priority,
            metadata=notification.metadata
        )
        return result
    except Exception as e:
        logger.error(f"Error creating notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    patient_id: Optional[str] = Query(None, description="ID del paciente (solo para cuidadores)"),
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Obtiene el número de notificaciones no leídas.
    """
    try:
        service = NotificationService(db)
        target_user_id = patient_id or user_id
        
        if patient_id and patient_id != user_id:
            has_access = await service.verify_patient_access(db, user_id, patient_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes permiso para ver las notificaciones de este paciente"
                )
        
        count = await service.get_unread_count(target_user_id)
        return {"unreadCount": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting unread count: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Marca una notificación como leída.
    """
    try:
        service = NotificationService(db)
        success = await service.mark_notification_read(notification_id)
        if not success:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")
        return {"message": "Notificación marcada como leída"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/read-all")
async def mark_all_notifications_read(
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Marca todas las notificaciones del usuario como leídas.
    """
    try:
        service = NotificationService(db)
        count = await service.mark_all_notifications_read(user_id)
        return {"message": f"Se marcaron {count} notificaciones como leídas"}
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Elimina una notificación.
    """
    try:
        service = NotificationService(db)
        success = await service.delete_notification(notification_id)
        if not success:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")
        return {"message": "Notificación eliminada"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# HEALTH TIPS ROUTES
# =====================

@router.get("/health-tips", response_model=List[HealthTipResponse])
async def get_health_tips(
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    limit: int = Query(10, ge=1, le=50, description="Límite de resultados"),
    patient_id: Optional[str] = Query(None, description="ID del paciente (solo para cuidadores)"),
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Obtiene los consejos de salud del usuario.
    """
    try:
        service = NotificationService(db)
        target_user_id = patient_id or user_id
        
        if patient_id and patient_id != user_id:
            has_access = await service.verify_patient_access(db, user_id, patient_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes permiso para ver los consejos de este paciente"
                )
        
        tips = await service.get_health_tips(
            user_id=target_user_id,
            category=category,
            limit=limit
        )
        return tips
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting health tips: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health-tips/random", response_model=Optional[HealthTipResponse])
async def get_random_health_tip(
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    patient_id: Optional[str] = Query(None, description="ID del paciente (solo para cuidadores)"),
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Obtiene un consejo de salud aleatorio.
    """
    try:
        service = NotificationService(db)
        target_user_id = patient_id or user_id
        
        if patient_id and patient_id != user_id:
            has_access = await service.verify_patient_access(db, user_id, patient_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes permiso para ver los consejos de este paciente"
                )
        
        tip = await service.get_random_health_tip(
            user_id=target_user_id,
            category=category
        )
        return tip
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting random health tip: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/health-tips", response_model=HealthTipResponse)
async def create_health_tip(
    tip: HealthTipCreate,
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Crea un nuevo consejo de salud.
    """
    try:
        service = NotificationService(db)
        result = await service.create_health_tip(
            user_id=user_id,
            category=tip.category,
            title=tip.title,
            content=tip.content,
            source=tip.source
        )
        return result
    except Exception as e:
        logger.error(f"Error creating health tip: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
