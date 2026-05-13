"""
MongoDB implementation of Health repository.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.repositories.health_repository import IHealthRepository
from src.core.exceptions import ResourceNotFoundException


class MongoHealthRepository(IHealthRepository):
    """
    MongoDB implementation of Health repository.
    
    Collections:
    - sensor_batches: Raw sensor data batches from mobile/watch
    - blood_pressure_readings: BP measurements
    - biometric_events: Anomaly detections and alerts
    - sync_requests: On-demand sync requests from caregivers
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.sensor_batches = db["sensor_batches"]
        self.bp_readings = db["blood_pressure_readings"]
        self.biometric_events = db["biometric_events"]
        self.sync_requests = db["sync_requests"]
    
    # === Base CRUD (using sensor_batches as primary) ===
    
    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Get sensor batch by ID."""
        try:
            return await self.sensor_batches.find_one({"_id": ObjectId(id)})
        except Exception:
            return None
    
    async def get_by_id_or_404(self, id: str) -> Dict[str, Any]:
        """Get sensor batch by ID or raise exception."""
        batch = await self.get_by_id(id)
        if not batch:
            raise ResourceNotFoundException("SensorBatch", id)
        return batch
    
    async def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find single sensor batch matching filter."""
        return await self.sensor_batches.find_one(filter)
    
    async def find_many(
        self, 
        filter: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """Find multiple sensor batches matching filter."""
        cursor = self.sensor_batches.find(filter).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        return await cursor.to_list(length=limit)
    
    async def insert_one(self, data: Dict[str, Any]) -> str:
        """Insert sensor batch."""
        result = await self.sensor_batches.insert_one(data)
        return str(result.inserted_id)
    
    async def update_one(self, id: str, update: Dict[str, Any]) -> bool:
        """Update sensor batch by ID."""
        result = await self.sensor_batches.update_one(
            {"_id": ObjectId(id)},
            update
        )
        return result.modified_count > 0
    
    async def delete_one(self, id: str) -> bool:
        """Delete sensor batch by ID."""
        result = await self.sensor_batches.delete_one({"_id": ObjectId(id)})
        return result.deleted_count > 0
    
    async def count(self, filter: Dict[str, Any]) -> int:
        """Count sensor batches matching filter."""
        return await self.sensor_batches.count_documents(filter)
    
    # === Sensor Batch Operations ===
    
    async def insert_sensor_batch(self, batch_data: Dict[str, Any]) -> str:
        """Insert sensor data batch."""
        result = await self.sensor_batches.insert_one(batch_data)
        return str(result.inserted_id)
    
    async def find_sensor_batches(
        self, 
        user_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Find sensor batches for user within date range."""
        query = {"userId": user_id}
        
        if start_date or end_date:
            query["createdAt"] = {}
            if start_date:
                query["createdAt"]["$gte"] = start_date
            if end_date:
                query["createdAt"]["$lte"] = end_date
        
        cursor = self.sensor_batches.find(query).sort("createdAt", -1).limit(limit)
        return await cursor.to_list(length=limit)
    
    # === Blood Pressure Operations ===
    
    async def insert_bp_reading(self, reading_data: Dict[str, Any]) -> str:
        """Insert blood pressure reading."""
        result = await self.bp_readings.insert_one(reading_data)
        return str(result.inserted_id)
    
    async def find_bp_readings(
        self, 
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Find BP readings for user within date range."""
        query = {"userId": user_id}
        
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date
        
        cursor = self.bp_readings.find(query).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)
    
    async def get_latest_bp(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get latest blood pressure reading for user."""
        return await self.bp_readings.find_one(
            {"userId": user_id},
            sort=[("timestamp", -1)]
        )
    
    # === Biometric Event Operations ===
    
    async def insert_biometric_event(self, event_data: Dict[str, Any]) -> str:
        """Insert biometric event."""
        result = await self.biometric_events.insert_one(event_data)
        return str(result.inserted_id)
    
    async def find_biometric_events(
        self, 
        user_id: str,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Find biometric events for user."""
        query = {"userId": user_id}
        
        if event_type:
            query["eventType"] = event_type
        
        if start_date:
            query["timestamp"] = {"$gte": start_date}
        
        cursor = self.biometric_events.find(query).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)
    
    # === Health Summary Operations ===
    
    async def get_latest_metrics(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get latest health metrics summary for user.
        
        Aggregates latest values from various sources.
        This is a simplified implementation - could be enhanced with aggregation pipeline.
        """
        # Get latest BP
        latest_bp = await self.get_latest_bp(user_id)
        
        # Get latest sensor batch
        latest_sensor = await self.sensor_batches.find_one(
            {"userId": user_id},
            sort=[("createdAt", -1)]
        )
        
        # Compile summary
        summary = {
            "userId": user_id,
            "bloodPressure": latest_bp if latest_bp else None,
            "latestSensorBatch": latest_sensor if latest_sensor else None
        }
        
        return summary
    
    async def get_heart_rate_history(
        self, 
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get heart rate samples for date range."""
        # Query sensor batches that contain heart rate data
        cursor = self.sensor_batches.find({
            "userId": user_id,
            "sensorType": "HEART_RATE",
            "createdAt": {
                "$gte": start_date,
                "$lte": end_date
            }
        }).sort("createdAt", 1)
        
        batches = await cursor.to_list(length=None)
        
        # Extract individual HR samples from batches
        hr_samples = []
        for batch in batches:
            if "samples" in batch:
                hr_samples.extend(batch["samples"])
        
        return hr_samples
    
    # === Sync Request Operations ===
    
    async def create_sync_request(
        self, 
        patient_id: str,
        requested_by: str
    ) -> str:
        """Create on-demand sync request."""
        request_data = {
            "patientId": patient_id,
            "requestedBy": requested_by,
            "status": "pending",
            "createdAt": datetime.utcnow()
        }
        result = await self.sync_requests.insert_one(request_data)
        return str(result.inserted_id)
    
    async def get_pending_sync_request(
        self, 
        patient_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get pending sync request for patient."""
        return await self.sync_requests.find_one({
            "patientId": patient_id,
            "status": "pending"
        })
    
    async def complete_sync_request(self, request_id: str) -> bool:
        """Mark sync request as completed."""
        result = await self.sync_requests.update_one(
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "status": "completed",
                    "completedAt": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
