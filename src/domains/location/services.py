"""
Business logic for location domain.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from src._config.logger import get_logger

logger = get_logger(__name__)

COLLECTION_NAME = "locations"
LOCATION_TTL_DAYS = 7


class LocationService:
    """Service for managing location tracking and sharing."""
    
    def __init__(self, db):
        self.db = db
        self.collection = db[COLLECTION_NAME]
    
    async def update_location(
        self,
        user_id: str,
        latitude: float,
        longitude: float,
        accuracy: Optional[float] = None,
        client_timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Update or insert user's current location.
        
        Args:
            user_id: ID of the user
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            accuracy: GPS accuracy in meters
            client_timestamp: Client-side timestamp in milliseconds
            
        Returns:
            Dict with success status and server timestamp
        """
        now = datetime.now(timezone.utc)
        
        # Convert client timestamp to datetime if provided
        client_dt = None
        if client_timestamp:
            client_dt = datetime.fromtimestamp(client_timestamp / 1000, tz=timezone.utc)
        
        location_doc = {
            "userId": user_id,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "clientTimestamp": client_dt,
            "createdAt": now
        }
        
        await self.collection.insert_one(location_doc)
        
        logger.info(f"Updated location for user {user_id}: ({latitude}, {longitude})")
        
        return {
            "success": True,
            "updated_at": int(now.timestamp() * 1000)
        }
    
    async def get_latest_location(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent location for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Location document or None
        """
        location = await self.collection.find_one(
            {"userId": user_id},
            sort=[("createdAt", -1)]
        )
        return location
    
    async def get_paired_user_location(self, user_id: str) -> Dict[str, Any]:
        """
        Get the location of the user's paired partner.
        
        This checks both directions:
        - If current user is patient, find their caregiver's location
        - If current user is caregiver, find their patient's location
        
        Args:
            user_id: ID of the requesting user
            
        Returns:
            Dict with found status and location (if found)
        """
        # Find active pairing where user is either patient or caregiver
        pairing = await self.db.pairings.find_one({
            "$or": [
                {"patientId": user_id, "status": "active"},
                {"caregiverId": user_id, "status": "active"}
            ]
        })
        
        if not pairing:
            return {
                "found": False,
                "message": "No tienes un usuario vinculado activo"
            }
        
        # Determine paired user ID
        if pairing["patientId"] == user_id:
            paired_user_id = pairing.get("caregiverId")
            paired_user_name = pairing.get("caregiverName", "Cuidador")
        else:
            paired_user_id = pairing["patientId"]
            paired_user_name = pairing.get("patientName", "Paciente")
        
        if not paired_user_id:
            return {
                "found": False,
                "message": "Usuario vinculado no disponible"
            }
        
        # Check if paired user has sharing enabled
        paired_user = await self.db.users.find_one({"_id": ObjectId(paired_user_id)})
        if paired_user and not paired_user.get("sharingLocation", True):
            return {
                "found": False,
                "message": "El usuario vinculado ha desactivado compartir ubicación"
            }
        
        # Get paired user's latest location
        location = await self.get_latest_location(paired_user_id)
        
        if not location:
            return {
                "found": False,
                "message": "No hay ubicación disponible del usuario vinculado"
            }
        
        # Check if location is recent (within last 30 minutes)
        location_age = datetime.now(timezone.utc) - location["createdAt"]
        if location_age > timedelta(minutes=30):
            return {
                "found": False,
                "message": "La última ubicación conocida es muy antigua"
            }
        
        return {
            "found": True,
            "location": {
                "user_id": paired_user_id,
                "user_name": paired_user_name,
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "accuracy": location.get("accuracy"),
                "updated_at": int(location["createdAt"].timestamp() * 1000)
            }
        }
    
    async def toggle_sharing(self, user_id: str, enabled: bool) -> Dict[str, Any]:
        """
        Toggle location sharing preference for a user.
        
        Args:
            user_id: ID of the user
            enabled: Whether sharing should be enabled
            
        Returns:
            Updated sharing status
        """
        result = await self.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"sharingLocation": enabled}}
        )
        
        if result.matched_count == 0:
            raise ValueError("User not found")
        
        logger.info(f"User {user_id} set location sharing to {enabled}")
        
        return {"sharing_enabled": enabled}
    
    async def get_sharing_status(self, user_id: str) -> Dict[str, Any]:
        """
        Get the current sharing status for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dict with sharing_enabled status
        """
        user = await self.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise ValueError("User not found")
        
        return {"sharing_enabled": user.get("sharingLocation", True)}
    
    async def get_location_history(
        self,
        user_id: str,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get location history for a user.
        
        Args:
            user_id: ID of the user
            hours: Number of hours to look back
            limit: Maximum number of locations to return
            
        Returns:
            List of location documents
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        cursor = self.collection.find(
            {
                "userId": user_id,
                "createdAt": {"$gte": since}
            },
            sort=[("createdAt", -1)],
            limit=limit
        )
        
        locations = []
        async for loc in cursor:
            locations.append({
                "user_id": user_id,
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "accuracy": loc.get("accuracy"),
                "updated_at": int(loc["createdAt"].timestamp() * 1000)
            })
        
        return locations
