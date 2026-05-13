"""
MongoDB implementation of User repository.
"""

from typing import Optional, Dict, Any, List
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.repositories.user_repository import IUserRepository
from src.core.exceptions import ResourceNotFoundException


class MongoUserRepository(IUserRepository):
    """
    MongoDB implementation of User repository.
    
    Collection: users
    """
    
    COLLECTION_NAME = "users"
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db[self.COLLECTION_NAME]
    
    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        try:
            return await self.collection.find_one({"_id": ObjectId(id)})
        except Exception:
            return None
    
    async def get_by_id_or_404(self, id: str) -> Dict[str, Any]:
        """Get user by ID or raise exception."""
        user = await self.get_by_id(id)
        if not user:
            raise ResourceNotFoundException("User", id)
        return user
    
    async def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find single user matching filter."""
        return await self.collection.find_one(filter)
    
    async def find_many(
        self, 
        filter: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """Find multiple users matching filter."""
        cursor = self.collection.find(filter).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        return await cursor.to_list(length=limit)
    
    async def insert_one(self, data: Dict[str, Any]) -> str:
        """Insert new user."""
        result = await self.collection.insert_one(data)
        return str(result.inserted_id)
    
    async def update_one(self, id: str, update: Dict[str, Any]) -> bool:
        """Update user by ID."""
        result = await self.collection.update_one(
            {"_id": ObjectId(id)},
            update
        )
        return result.modified_count > 0
    
    async def delete_one(self, id: str) -> bool:
        """Delete user by ID."""
        result = await self.collection.delete_one({"_id": ObjectId(id)})
        return result.deleted_count > 0
    
    async def count(self, filter: Dict[str, Any]) -> int:
        """Count users matching filter."""
        return await self.collection.count_documents(filter)
    
    # === User-specific methods ===
    
    async def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find user by email address."""
        return await self.collection.find_one({"email": email})
    
    async def find_by_google_id(self, google_id: str) -> Optional[Dict[str, Any]]:
        """Find user by Google OAuth ID."""
        return await self.collection.find_one({"googleId": google_id})
    
    async def find_by_profile_data(
        self, 
        name: str, 
        birthdate: str, 
        height: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find user by profile data.
        
        Matches on name and birthdate. Height is optional for stricter matching.
        """
        query = {
            "name": name,
            "birthdate": birthdate
        }
        
        if height is not None:
            query["height"] = height
        
        return await self.collection.find_one(query)
    
    async def update_fcm_token(self, user_id: str, fcm_token: str) -> bool:
        """Update user's FCM token."""
        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"fcmToken": fcm_token}}
        )
        return result.modified_count > 0
    
    async def update_location(
        self, 
        user_id: str, 
        location: Dict[str, Any]
    ) -> bool:
        """Update user's last known location."""
        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"lastLocation": location}}
        )
        return result.modified_count > 0
