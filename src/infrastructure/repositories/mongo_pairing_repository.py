"""
MongoDB implementation of Pairing repository.
"""

from typing import Optional, Dict, Any, List
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.repositories.pairing_repository import IPairingRepository
from src.core.exceptions import ResourceNotFoundException


class MongoPairingRepository(IPairingRepository):
    """
    MongoDB implementation of Pairing repository.
    
    Collection: pairings
    """
    
    COLLECTION_NAME = "pairings"
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db[self.COLLECTION_NAME]
    
    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Get pairing by ID."""
        try:
            return await self.collection.find_one({"_id": ObjectId(id)})
        except Exception:
            return None
    
    async def get_by_id_or_404(self, id: str) -> Dict[str, Any]:
        """Get pairing by ID or raise exception."""
        pairing = await self.get_by_id(id)
        if not pairing:
            raise ResourceNotFoundException("Pairing", id)
        return pairing
    
    async def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find single pairing matching filter."""
        return await self.collection.find_one(filter)
    
    async def find_many(
        self, 
        filter: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """Find multiple pairings matching filter."""
        cursor = self.collection.find(filter).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        return await cursor.to_list(length=limit)
    
    async def insert_one(self, data: Dict[str, Any]) -> str:
        """Insert new pairing."""
        result = await self.collection.insert_one(data)
        return str(result.inserted_id)
    
    async def update_one(self, id: str, update: Dict[str, Any]) -> bool:
        """Update pairing by ID."""
        result = await self.collection.update_one(
            {"_id": ObjectId(id)},
            update
        )
        return result.modified_count > 0
    
    async def delete_one(self, id: str) -> bool:
        """Delete pairing by ID."""
        result = await self.collection.delete_one({"_id": ObjectId(id)})
        return result.deleted_count > 0
    
    async def count(self, filter: Dict[str, Any]) -> int:
        """Count pairings matching filter."""
        return await self.collection.count_documents(filter)
    
    # === Pairing-specific methods ===
    
    async def find_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Find pairing by unique code."""
        return await self.collection.find_one({"code": code})
    
    async def find_active_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """Find all active pairings for a patient."""
        cursor = self.collection.find({
            "patientId": patient_id,
            "status": "active"
        })
        return await cursor.to_list(length=None)
    
    async def find_active_by_caregiver(self, caregiver_id: str) -> List[Dict[str, Any]]:
        """Find all active pairings for a caregiver."""
        cursor = self.collection.find({
            "caregiverId": caregiver_id,
            "status": "active"
        })
        return await cursor.to_list(length=None)
    
    async def find_relationship(
        self, 
        caregiver_id: str, 
        patient_id: str
    ) -> Optional[Dict[str, Any]]:
        """Find pairing relationship between caregiver and patient."""
        return await self.collection.find_one({
            "caregiverId": caregiver_id,
            "patientId": patient_id,
            "status": "active"
        })
    
    async def verify_access(
        self, 
        requester_id: str, 
        patient_id: str
    ) -> bool:
        """
        Verify if requester has access to patient's data.
        
        Returns True if:
        - Requester IS the patient, OR
        - Active pairing exists between requester (caregiver) and patient
        """
        # Self-access always allowed
        if requester_id == patient_id:
            return True
        
        # Check for active caregiver-patient relationship
        pairing = await self.find_relationship(requester_id, patient_id)
        return pairing is not None
    
    async def create_pending_pairing(
        self, 
        patient_id: str, 
        code: str, 
        expires_at: Any
    ) -> str:
        """Create pending pairing with unique code."""
        pairing_data = {
            "patientId": patient_id,
            "code": code,
            "status": "pending",
            "expiresAt": expires_at,
            "caregiverId": None
        }
        result = await self.collection.insert_one(pairing_data)
        return str(result.inserted_id)
    
    async def activate_pairing(
        self, 
        code: str, 
        caregiver_id: str
    ) -> bool:
        """Activate pending pairing by associating caregiver."""
        result = await self.collection.update_one(
            {"code": code, "status": "pending"},
            {
                "$set": {
                    "caregiverId": caregiver_id,
                    "status": "active"
                }
            }
        )
        return result.modified_count > 0
    
    async def deactivate_pairing(self, pairing_id: str) -> bool:
        """Deactivate (soft delete) pairing relationship."""
        result = await self.collection.update_one(
            {"_id": ObjectId(pairing_id)},
            {"$set": {"status": "inactive"}}
        )
        return result.modified_count > 0
