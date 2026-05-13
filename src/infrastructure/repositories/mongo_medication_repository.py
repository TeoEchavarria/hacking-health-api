"""
MongoDB implementation of Medication repository.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.repositories.medication_repository import IMedicationRepository
from src.core.exceptions import ResourceNotFoundException


class MongoMedicationRepository(IMedicationRepository):
    """
    MongoDB implementation of Medication repository.
    
    Collections:
    - medications: Medication definitions for users
    - medication_logs: Intake log entries
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.medications = db["medications"]
        self.medication_logs = db["medication_logs"]
    
    # === Base CRUD (using medications as primary) ===
    
    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Get medication by ID."""
        try:
            return await self.medications.find_one({"_id": ObjectId(id)})
        except Exception:
            return None
    
    async def get_by_id_or_404(self, id: str) -> Dict[str, Any]:
        """Get medication by ID or raise exception."""
        medication = await self.get_by_id(id)
        if not medication:
            raise ResourceNotFoundException("Medication", id)
        return medication
    
    async def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find single medication matching filter."""
        return await self.medications.find_one(filter)
    
    async def find_many(
        self, 
        filter: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """Find multiple medications matching filter."""
        cursor = self.medications.find(filter).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        return await cursor.to_list(length=limit)
    
    async def insert_one(self, data: Dict[str, Any]) -> str:
        """Insert medication."""
        result = await self.medications.insert_one(data)
        return str(result.inserted_id)
    
    async def update_one(self, id: str, update: Dict[str, Any]) -> bool:
        """Update medication by ID."""
        result = await self.medications.update_one(
            {"_id": ObjectId(id)},
            update
        )
        return result.modified_count > 0
    
    async def delete_one(self, id: str) -> bool:
        """Delete medication by ID."""
        result = await self.medications.delete_one({"_id": ObjectId(id)})
        return result.deleted_count > 0
    
    async def count(self, filter: Dict[str, Any]) -> int:
        """Count medications matching filter."""
        return await self.medications.count_documents(filter)
    
    # === Medication-specific methods ===
    
    async def find_by_user(
        self, 
        user_id: str,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Find medications for user."""
        query = {"userId": user_id}
        
        if active_only:
            query["active"] = True
        
        cursor = self.medications.find(query).sort("createdAt", -1)
        return await cursor.to_list(length=None)
    
    async def find_by_id_and_user(
        self, 
        medication_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Find medication by ID, ensuring it belongs to the user."""
        try:
            return await self.medications.find_one({
                "_id": ObjectId(medication_id),
                "userId": user_id
            })
        except Exception:
            return None
    
    async def create_medication(
        self, 
        user_id: str,
        medication_data: Dict[str, Any]
    ) -> str:
        """Create new medication entry for user."""
        medication_data["userId"] = user_id
        medication_data["active"] = True
        medication_data["createdAt"] = datetime.utcnow()
        
        result = await self.medications.insert_one(medication_data)
        return str(result.inserted_id)
    
    async def deactivate_medication(self, medication_id: str) -> bool:
        """Deactivate (soft delete) medication."""
        result = await self.medications.update_one(
            {"_id": ObjectId(medication_id)},
            {"$set": {"active": False, "deactivatedAt": datetime.utcnow()}}
        )
        return result.modified_count > 0
    
    # === Medication Log Operations ===
    
    async def create_log_entry(
        self, 
        medication_id: str,
        user_id: str,
        taken_at: datetime,
        notes: Optional[str] = None
    ) -> str:
        """Log medication intake."""
        log_data = {
            "medicationId": medication_id,
            "userId": user_id,
            "takenAt": taken_at,
            "notes": notes,
            "createdAt": datetime.utcnow()
        }
        
        result = await self.medication_logs.insert_one(log_data)
        return str(result.inserted_id)
    
    async def find_log_entries(
        self, 
        user_id: str,
        medication_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Find medication log entries for user."""
        query = {"userId": user_id}
        
        if medication_id:
            query["medicationId"] = medication_id
        
        if start_date or end_date:
            query["takenAt"] = {}
            if start_date:
                query["takenAt"]["$gte"] = start_date
            if end_date:
                query["takenAt"]["$lte"] = end_date
        
        cursor = self.medication_logs.find(query).sort("takenAt", -1).limit(limit)
        return await cursor.to_list(length=limit)
