"""
Base repository interface with common CRUD operations.

Provides generic type-safe repository pattern implementation.
All concrete repositories should inherit from this base.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Dict, Any
from bson import ObjectId

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository providing common database operations.
    
    Generic type T represents the domain model/document type.
    Implementations must provide concrete database access logic.
    """
    
    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve document by ID.
        
        Args:
            id: Document ID as string
            
        Returns:
            Document dict if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def get_by_id_or_404(self, id: str) -> Dict[str, Any]:
        """
        Retrieve document by ID or raise exception if not found.
        
        Args:
            id: Document ID as string
            
        Returns:
            Document dict
            
        Raises:
            ResourceNotFoundException: If document not found
        """
        pass
    
    @abstractmethod
    async def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find single document matching filter.
        
        Args:
            filter: MongoDB query filter
            
        Returns:
            Document dict if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def find_many(
        self, 
        filter: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Find multiple documents matching filter.
        
        Args:
            filter: MongoDB query filter
            skip: Number of documents to skip (pagination)
            limit: Maximum number of documents to return
            sort: Sort specification [(field, direction), ...]
            
        Returns:
            List of document dicts
        """
        pass
    
    @abstractmethod
    async def insert_one(self, data: Dict[str, Any]) -> str:
        """
        Insert single document.
        
        Args:
            data: Document data to insert
            
        Returns:
            Inserted document ID as string
        """
        pass
    
    @abstractmethod
    async def update_one(self, id: str, update: Dict[str, Any]) -> bool:
        """
        Update single document by ID.
        
        Args:
            id: Document ID as string
            update: Update operations (e.g., {"$set": {...}})
            
        Returns:
            True if document was updated, False otherwise
        """
        pass
    
    @abstractmethod
    async def delete_one(self, id: str) -> bool:
        """
        Delete single document by ID.
        
        Args:
            id: Document ID as string
            
        Returns:
            True if document was deleted, False otherwise
        """
        pass
    
    @abstractmethod
    async def count(self, filter: Dict[str, Any]) -> int:
        """
        Count documents matching filter.
        
        Args:
            filter: MongoDB query filter
            
        Returns:
            Number of matching documents
        """
        pass
    
    def _to_object_id(self, id: str) -> ObjectId:
        """
        Convert string ID to MongoDB ObjectId.
        
        Args:
            id: String ID
            
        Returns:
            ObjectId instance
            
        Raises:
            ValueError: If ID string is invalid
        """
        try:
            return ObjectId(id)
        except Exception as e:
            raise ValueError(f"Invalid ObjectId: {id}") from e
