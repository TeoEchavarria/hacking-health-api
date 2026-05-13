"""
Sync Service.

Handles on-demand sync request management between caregivers and patients:
- Create sync requests (caregiver initiated)
- Check pending sync requests (patient device polling)
- Mark sync requests as complete

Following Single Responsibility Principle (SRP).
"""
from typing import Dict, Any
from datetime import datetime, timezone
from bson import ObjectId
from src._config.logger import get_logger

logger = get_logger(__name__)


class SyncService:
    """Service for managing on-demand sync requests."""
    
    def __init__(self, db):
        self.db = db
    
    async def create_sync_request(
        self,
        patient_id: str,
        requested_by: str,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """
        Create a sync request for a patient.
        Called by caregiver to request immediate sync.
        
        Args:
            patient_id: ID of the patient to sync
            requested_by: ID of the caregiver requesting sync
            priority: Request priority (normal|urgent)
            
        Returns:
            Dict with request_id, patient_id, requested_by, status, created_at
        """
        now = datetime.now(timezone.utc)
        request_doc = {
            "patient_id": patient_id,
            "requested_by": requested_by,
            "priority": priority,
            "status": "pending",
            "created_at": now,
            "completed_at": None
        }
        
        result = await self.db.sync_requests.insert_one(request_doc)
        
        logger.info(
            f"Sync request created: {result.inserted_id} "
            f"for patient {patient_id} by {requested_by}"
        )
        
        return {
            "request_id": str(result.inserted_id),
            "patient_id": patient_id,
            "requested_by": requested_by,
            "status": "pending",
            "created_at": int(now.timestamp() * 1000)
        }
    
    async def get_pending_sync_request(
        self,
        patient_id: str
    ) -> Dict[str, Any]:
        """
        Get the oldest pending sync request for a patient.
        Called by patient's device to check if sync is needed.
        
        Args:
            patient_id: ID of the patient
            
        Returns:
            Dict with has_pending, request_id, requested_by, priority, created_at
        """
        # Find oldest pending request
        request = await self.db.sync_requests.find_one(
            {
                "patient_id": patient_id,
                "status": "pending"
            },
            sort=[("created_at", 1)]  # FIFO - oldest first
        )
        
        if not request:
            return {"has_pending": False}
        
        return {
            "has_pending": True,
            "request_id": str(request["_id"]),
            "requested_by": request.get("requested_by"),
            "priority": request.get("priority", "normal"),
            "created_at": int(request["created_at"].timestamp() * 1000)
        }
    
    async def complete_sync_request(
        self,
        request_id: str,
        metrics_synced: int = 0
    ) -> Dict[str, Any]:
        """
        Mark a sync request as complete.
        Called by patient's device after syncing.
        
        Args:
            request_id: ID of the sync request
            metrics_synced: Number of metrics synced
            
        Returns:
            Dict with success, message
        """
        now = datetime.now(timezone.utc)
        
        result = await self.db.sync_requests.update_one(
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": now,
                    "metrics_synced": metrics_synced
                }
            }
        )
        
        if result.modified_count == 0:
            return {
                "success": False,
                "message": "Solicitud de sync no encontrada"
            }
        
        logger.info(f"Sync request {request_id} completed with {metrics_synced} metrics")
        
        return {
            "success": True,
            "message": "Sincronización completada"
        }
