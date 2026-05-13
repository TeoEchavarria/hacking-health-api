"""
Pairing repository interface for caregiver-patient relationships.
"""

from abc import abstractmethod
from typing import Optional, List, Dict, Any
from .base import BaseRepository


class IPairingRepository(BaseRepository):
    """
    Pairing repository interface for caregiver-patient relationship operations.
    
    Manages pairing codes, relationship creation, and access verification.
    """
    
    @abstractmethod
    async def find_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Find pairing by unique code.
        
        Args:
            code: 6-character pairing code
            
        Returns:
            Pairing document if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def find_active_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Find all active pairings for a patient.
        
        Args:
            patient_id: Patient user ID
            
        Returns:
            List of active pairing documents
        """
        pass
    
    @abstractmethod
    async def find_active_by_caregiver(self, caregiver_id: str) -> List[Dict[str, Any]]:
        """
        Find all active pairings for a caregiver.
        
        Args:
            caregiver_id: Caregiver user ID
            
        Returns:
            List of active pairing documents
        """
        pass
    
    @abstractmethod
    async def find_relationship(
        self, 
        caregiver_id: str, 
        patient_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find pairing relationship between caregiver and patient.
        
        Args:
            caregiver_id: Caregiver user ID
            patient_id: Patient user ID
            
        Returns:
            Pairing document if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def verify_access(
        self, 
        requester_id: str, 
        patient_id: str
    ) -> bool:
        """
        Verify if requester has access to patient's data.
        
        Checks if:
        - Requester is the patient themselves, OR
        - Active pairing exists between requester (caregiver) and patient
        
        Args:
            requester_id: User ID requesting access
            patient_id: Patient user ID
            
        Returns:
            True if access is granted, False otherwise
        """
        pass
    
    @abstractmethod
    async def create_pending_pairing(
        self, 
        patient_id: str, 
        code: str, 
        expires_at: Any
    ) -> str:
        """
        Create pending pairing with unique code.
        
        Args:
            patient_id: Patient user ID creating the pairing
            code: Unique 6-character code
            expires_at: Expiration datetime
            
        Returns:
            Created pairing document ID
        """
        pass
    
    @abstractmethod
    async def activate_pairing(
        self, 
        code: str, 
        caregiver_id: str
    ) -> bool:
        """
        Activate pending pairing by associating caregiver.
        
        Args:
            code: Pairing code
            caregiver_id: Caregiver user ID
            
        Returns:
            True if activated successfully
        """
        pass
    
    @abstractmethod
    async def deactivate_pairing(self, pairing_id: str) -> bool:
        """
        Deactivate (soft delete) pairing relationship.
        
        Args:
            pairing_id: Pairing document ID
            
        Returns:
            True if deactivated successfully
        """
        pass
