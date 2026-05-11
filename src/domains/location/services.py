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
LOCATION_STALE_MINUTES = 15  # Mark location as stale after 15 minutes


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
        Update user's current location using upsert on User document.
        
        This method:
        1. Updates lastLocation embedded in the User document (primary source)
        2. Optionally inserts into locations collection for history (with TTL)
        
        GeoJSON format: coordinates are [longitude, latitude] (lng first!)
        
        Args:
            user_id: ID of the user
            latitude: Latitude coordinate (-90 to 90)
            longitude: Longitude coordinate (-180 to 180)
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
        
        # GeoJSON Point format: coordinates are [longitude, latitude]
        last_location = {
            "type": "Point",
            "coordinates": [longitude, latitude],  # GeoJSON: lng first, lat second
            "accuracy": accuracy,
            "updatedAt": now
        }
        
        # Update User document with lastLocation (upsert pattern - no document growth)
        await self.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"lastLocation": last_location}}
        )
        
        # Also insert into history collection (for tracking/analytics, auto-expires via TTL)
        history_doc = {
            "userId": user_id,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "clientTimestamp": client_dt,
            "createdAt": now
        }
        await self.collection.insert_one(history_doc)
        
        logger.info(f"Updated location for user {user_id}: ({latitude}, {longitude})")
        
        return {
            "success": True,
            "updated_at": int(now.timestamp() * 1000)
        }
    
    async def get_user_with_location(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user document with lastLocation.
        
        Args:
            user_id: ID of the user
            
        Returns:
            User document with name, avatar, lastLocation, sharingLocation, role
        """
        user = await self.db.users.find_one(
            {"_id": ObjectId(user_id)},
            {"name": 1, "profilePicture": 1, "lastLocation": 1, "sharingLocation": 1, "role": 1}
        )
        return user
    
    async def get_latest_location(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent location for a user from history collection.
        (Legacy method for backwards compatibility)
        
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
        Get locations of both self and paired partner.
        
        Returns self.location and partner.location with metadata including:
        - locationStale: true if location is older than 15 minutes
        - lastSeenAt: timestamp of last location update
        - role: 'patient' or 'caregiver'
        
        This allows the app to:
        - Show both markers on the map
        - Display stale warning for outdated locations
        - Handle cases where partner disabled sharing
        
        Args:
            user_id: ID of the requesting user
            
        Returns:
            Dict with self and partner location data
        """
        now = datetime.now(timezone.utc)
        
        # Get current user data
        current_user = await self.get_user_with_location(user_id)
        if not current_user:
            return {
                "self": None,
                "partner": None,
                "message": "Usuario no encontrado"
            }
        
        # Build self location data
        self_location = None
        if current_user.get("lastLocation"):
            loc = current_user["lastLocation"]
            coordinates = loc.get("coordinates", [])
            if len(coordinates) == 2:
                self_location = {
                    "latitude": coordinates[1],  # GeoJSON: [lng, lat]
                    "longitude": coordinates[0],
                    "accuracy": loc.get("accuracy"),
                    "updatedAt": int(loc["updatedAt"].timestamp() * 1000) if loc.get("updatedAt") else None
                }
        
        self_data = {
            "name": current_user.get("name", "Yo"),
            "avatar": current_user.get("profilePicture"),
            "role": current_user.get("role", "patient"),
            "location": self_location,
            "sharingEnabled": current_user.get("sharingLocation", True)
        }
        
        # Find active pairing where user is either patient or caregiver
        pairing = await self.db.pairings.find_one({
            "$or": [
                {"patientId": user_id, "status": "active"},
                {"caregiverId": user_id, "status": "active"}
            ]
        })
        
        if not pairing:
            return {
                "self": self_data,
                "partner": None,
                "hasRelation": False,
                "message": "No tienes un usuario vinculado activo"
            }
        
        # Determine partner info based on current user's role in pairing
        if pairing["patientId"] == user_id:
            # Current user is patient, partner is caregiver
            paired_user_id = pairing.get("caregiverId")
            default_partner_name = pairing.get("caregiverName", "Cuidador")
            partner_role = "caregiver"
        else:
            # Current user is caregiver, partner is patient
            paired_user_id = pairing["patientId"]
            default_partner_name = pairing.get("patientName", "Paciente")
            partner_role = "patient"
        
        if not paired_user_id:
            return {
                "self": self_data,
                "partner": None,
                "hasRelation": True,
                "message": "Usuario vinculado no disponible"
            }
        
        # Get partner user data
        partner_user = await self.get_user_with_location(paired_user_id)
        
        if not partner_user:
            return {
                "self": self_data,
                "partner": {
                    "name": default_partner_name,
                    "avatar": None,
                    "role": partner_role,
                    "location": None,
                    "locationStale": False,
                    "lastSeenAt": None,
                    "sharingEnabled": True,
                    "sharingDisabledMessage": None
                },
                "hasRelation": True
            }
        
        # Check if partner has sharing enabled
        partner_sharing_enabled = partner_user.get("sharingLocation", True)
        
        # Build partner location data
        partner_location = None
        location_stale = False
        last_seen_at = None
        sharing_disabled_message = None
        
        if not partner_sharing_enabled:
            sharing_disabled_message = "Este usuario ha desactivado compartir ubicación"
        elif partner_user.get("lastLocation"):
            loc = partner_user["lastLocation"]
            coordinates = loc.get("coordinates", [])
            updated_at = loc.get("updatedAt")
            
            if len(coordinates) == 2 and updated_at:
                partner_location = {
                    "latitude": coordinates[1],  # GeoJSON: [lng, lat]
                    "longitude": coordinates[0],
                    "accuracy": loc.get("accuracy"),
                    "updatedAt": int(updated_at.timestamp() * 1000)
                }
                last_seen_at = int(updated_at.timestamp() * 1000)
                
                # Check if location is stale (> 15 minutes old)
                location_age = now - updated_at
                if location_age > timedelta(minutes=LOCATION_STALE_MINUTES):
                    location_stale = True
        
        partner_data = {
            "name": partner_user.get("name") or default_partner_name,
            "avatar": partner_user.get("profilePicture"),
            "role": partner_role,
            "location": partner_location,
            "locationStale": location_stale,
            "lastSeenAt": last_seen_at,
            "sharingEnabled": partner_sharing_enabled,
            "sharingDisabledMessage": sharing_disabled_message
        }
        
        return {
            "self": self_data,
            "partner": partner_data,
            "hasRelation": True
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
