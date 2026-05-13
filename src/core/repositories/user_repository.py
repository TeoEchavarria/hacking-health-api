"""
User repository interface with user-specific operations.
"""

from abc import abstractmethod
from typing import Optional, Dict, Any
from .base import BaseRepository


class IUserRepository(BaseRepository):
    """
    User repository interface for user document operations.
    
    Extends BaseRepository with user-specific query methods.
    """
    
    @abstractmethod
    async def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Find user by email address.
        
        Args:
            email: User email address
            
        Returns:
            User document if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def find_by_google_id(self, google_id: str) -> Optional[Dict[str, Any]]:
        """
        Find user by Google OAuth ID.
        
        Args:
            google_id: Google OAuth user ID
            
        Returns:
            User document if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def find_by_profile_data(
        self, 
        name: str, 
        birthdate: str, 
        height: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find user by profile data (name, birthdate, optional height).
        
        Used for profile-based authentication from Samsung Health.
        
        Args:
            name: User full name
            birthdate: User birthdate (ISO format)
            height: User height in cm (optional for matching)
            
        Returns:
            User document if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def update_fcm_token(self, user_id: str, fcm_token: str) -> bool:
        """
        Update user's FCM (Firebase Cloud Messaging) token.
        
        Args:
            user_id: User ID
            fcm_token: New FCM token
            
        Returns:
            True if updated successfully
        """
        pass
    
    @abstractmethod
    async def update_location(
        self, 
        user_id: str, 
        location: Dict[str, Any]
    ) -> bool:
        """
        Update user's last known location.
        
        Args:
            user_id: User ID
            location: GeoJSON location data
            
        Returns:
            True if updated successfully
        """
        pass
