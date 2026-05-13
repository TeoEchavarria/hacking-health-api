"""
Health repository interface for health metrics and sensor data.
"""

from abc import abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
from .base import BaseRepository


class IHealthRepository(BaseRepository):
    """
    Health repository interface for health metrics operations.
    
    Manages sensor batches, blood pressure readings, biometric events, and summaries.
    """
    
    # === Sensor Batch Operations ===
    
    @abstractmethod
    async def insert_sensor_batch(self, batch_data: Dict[str, Any]) -> str:
        """
        Insert sensor data batch.
        
        Args:
            batch_data: Sensor batch document with userId, samples, etc.
            
        Returns:
            Inserted batch document ID
        """
        pass
    
    @abstractmethod
    async def find_sensor_batches(
        self, 
        user_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find sensor batches for user within date range.
        
        Args:
            user_id: User ID
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            limit: Maximum number of batches to return
            
        Returns:
            List of sensor batch documents
        """
        pass
    
    # === Blood Pressure Operations ===
    
    @abstractmethod
    async def insert_bp_reading(self, reading_data: Dict[str, Any]) -> str:
        """
        Insert blood pressure reading.
        
        Args:
            reading_data: BP reading document
            
        Returns:
            Inserted reading document ID
        """
        pass
    
    @abstractmethod
    async def find_bp_readings(
        self, 
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find blood pressure readings for user within date range.
        
        Args:
            user_id: User ID
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            limit: Maximum number of readings to return
            
        Returns:
            List of BP reading documents, sorted by timestamp desc
        """
        pass
    
    @abstractmethod
    async def get_latest_bp(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get latest blood pressure reading for user.
        
        Args:
            user_id: User ID
            
        Returns:
            Latest BP reading document, or None
        """
        pass
    
    # === Biometric Event Operations ===
    
    @abstractmethod
    async def insert_biometric_event(self, event_data: Dict[str, Any]) -> str:
        """
        Insert biometric event (alert, anomaly detection).
        
        Args:
            event_data: Event document
            
        Returns:
            Inserted event document ID
        """
        pass
    
    @abstractmethod
    async def find_biometric_events(
        self, 
        user_id: str,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Find biometric events for user.
        
        Args:
            user_id: User ID
            event_type: Filter by event type (e.g., 'heart_rate_anomaly')
            start_date: Events after this date
            limit: Maximum number of events to return
            
        Returns:
            List of biometric event documents
        """
        pass
    
    # === Health Summary Operations ===
    
    @abstractmethod
    async def get_latest_metrics(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get latest health metrics summary for user.
        
        Aggregates latest values from various health data sources.
        
        Args:
            user_id: User ID
            
        Returns:
            Summary document with latest metrics, or None
        """
        pass
    
    @abstractmethod
    async def get_heart_rate_history(
        self, 
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get heart rate samples for date range.
        
        Args:
            user_id: User ID
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            List of heart rate data points
        """
        pass
    
    # === Sync Request Operations ===
    
    @abstractmethod
    async def create_sync_request(
        self, 
        patient_id: str,
        requested_by: str
    ) -> str:
        """
        Create on-demand sync request.
        
        Args:
            patient_id: Patient user ID to sync
            requested_by: Caregiver ID making the request
            
        Returns:
            Sync request document ID
        """
        pass
    
    @abstractmethod
    async def get_pending_sync_request(
        self, 
        patient_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get pending sync request for patient.
        
        Args:
            patient_id: Patient user ID
            
        Returns:
            Pending sync request document, or None
        """
        pass
    
    @abstractmethod
    async def complete_sync_request(self, request_id: str) -> bool:
        """
        Mark sync request as completed.
        
        Args:
            request_id: Sync request document ID
            
        Returns:
            True if updated successfully
        """
        pass
