"""
Medication repository interface for medication tracking.
"""

from abc import abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
from .base import BaseRepository


class IMedicationRepository(BaseRepository):
    """
    Medication repository interface for medication management operations.
    
    Manages medications and medication log entries.
    """
    
    @abstractmethod
    async def find_by_user(
        self, 
        user_id: str,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find medications for user.
        
        Args:
            user_id: User ID
            active_only: If True, only return active medications
            
        Returns:
            List of medication documents
        """
        pass
    
    @abstractmethod
    async def find_by_id_and_user(
        self, 
        medication_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find medication by ID, ensuring it belongs to the user.
        
        Args:
            medication_id: Medication document ID
            user_id: User ID to verify ownership
            
        Returns:
            Medication document if found and belongs to user, None otherwise
        """
        pass
    
    @abstractmethod
    async def create_medication(
        self, 
        user_id: str,
        medication_data: Dict[str, Any]
    ) -> str:
        """
        Create new medication entry for user.
        
        Args:
            user_id: User ID
            medication_data: Medication details (name, dosage, frequency, etc.)
            
        Returns:
            Created medication document ID
        """
        pass
    
    @abstractmethod
    async def deactivate_medication(self, medication_id: str) -> bool:
        """
        Deactivate (soft delete) medication.
        
        Args:
            medication_id: Medication document ID
            
        Returns:
            True if deactivated successfully
        """
        pass
    
    # === Medication Log Operations ===
    
    @abstractmethod
    async def create_log_entry(
        self, 
        medication_id: str,
        user_id: str,
        taken_at: datetime,
        notes: Optional[str] = None
    ) -> str:
        """
        Log medication intake.
        
        Args:
            medication_id: Medication document ID
            user_id: User ID
            taken_at: Timestamp when medication was taken
            notes: Optional notes
            
        Returns:
            Created log entry document ID
        """
        pass
    
    @abstractmethod
    async def find_log_entries(
        self, 
        user_id: str,
        medication_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find medication log entries for user.
        
        Args:
            user_id: User ID
            medication_id: Filter by specific medication (optional)
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            limit: Maximum number of entries to return
            
        Returns:
            List of log entry documents, sorted by taken_at desc
        """
        pass
