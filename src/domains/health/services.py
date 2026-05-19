"""
Health Service - Façade Pattern.

This class acts as a façade, delegating to specialized services:
- PatientDataService: Patient queries
- HealthMetricsService: Metrics ingestion
- SyncService: Sync management
- BloodPressureService: BP/HR storage and history

The verify_patient_access() method is deprecated in favor of AuthorizationService.

Following Single Responsibility and Façade patterns.
"""
from typing import Optional, Dict, Any, List
from src.domains.health.service_modules import (
    PatientDataService,
    HealthMetricsService,
    SyncService,
    BloodPressureService
)


class HealthService:
    """
    Façade for health domain services.
    
    Delegates to specialized services while maintaining backward compatibility.
    """
    
    def __init__(self, db):
        self.db = db
        # Initialize specialized services
        self._patient_data = PatientDataService(db)
        self._health_metrics = HealthMetricsService(db)
        self._sync = SyncService(db)
        self._blood_pressure = BloodPressureService(db)
    
    # =========================================
    # DEPRECATED: Authorization (use AuthorizationService instead)
    # =========================================
    
    async def verify_patient_access(
        self,
        requester_id: str,
        patient_id: str
    ) -> bool:
        """
        DEPRECATED: Use src.core.authorization.AuthorizationService instead.
        
        This method is kept for backward compatibility but should be replaced
        with AuthorizationService.verify_patient_access().
        """
        # Import here to avoid circular dependency
        from src.core.authorization import get_authorization_service
        
        auth_service = get_authorization_service(self.db)
        return await auth_service.verify_patient_access(requester_id, patient_id)
    
    # =========================================
    # Patient Data Queries - Delegate to PatientDataService
    # =========================================
    
    async def get_patient_sensor_data(
        self,
        patient_id: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get sensor data for a patient."""
        return await self._patient_data.get_patient_sensor_data(
            patient_id, start_time, end_time, limit
        )
    
    async def get_patient_alerts(
        self,
        patient_id: str,
        cursor: Optional[str] = None,
        limit: int = 50,
        severity: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get alerts for a patient."""
        return await self._patient_data.get_patient_alerts(
            patient_id, cursor, limit, severity
        )
    
    async def get_patient_health_summary(
        self,
        patient_id: str
    ) -> Dict[str, Any]:
        """Get health summary for a patient (last 24 hours)."""
        return await self._patient_data.get_patient_health_summary(patient_id)
    
    async def get_biometrics_history(
        self,
        user_id: str,
        limit: int = 50,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get biometric history for a user."""
        return await self._patient_data.get_biometrics_history(user_id, limit, days)
    
    # =========================================
    # Health Metrics - Delegate to HealthMetricsService
    # =========================================
    
    async def ingest_health_metrics(self, metrics) -> Dict[str, Any]:
        """Ingest health metrics from watch (via phone)."""
        return await self._health_metrics.ingest_health_metrics(metrics)

    async def get_steps_history(
        self,
        patient_id: str,
        date_from=None,
        date_to=None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """Steps history for a patient (caregiver/self-read)."""
        return await self._health_metrics.get_steps_history(
            patient_id, date_from, date_to, limit
        )

    async def get_sleep_history(
        self,
        patient_id: str,
        date_from=None,
        date_to=None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """Sleep history for a patient (caregiver/self-read)."""
        return await self._health_metrics.get_sleep_history(
            patient_id, date_from, date_to, limit
        )

    async def get_30day_summary(self, patient_id: str) -> Dict[str, Any]:
        """Rolling 30-day aggregated summary for a patient."""
        return await self._health_metrics.get_30day_summary(patient_id)
    
    # =========================================
    # Sync Management - Delegate to SyncService
    # =========================================
    
    async def create_sync_request(
        self,
        patient_id: str,
        requested_by: str,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """Create a sync request for a patient."""
        return await self._sync.create_sync_request(patient_id, requested_by, priority)
    
    async def get_pending_sync_request(
        self,
        patient_id: str
    ) -> Dict[str, Any]:
        """Get the oldest pending sync request for a patient."""
        return await self._sync.get_pending_sync_request(patient_id)
    
    async def complete_sync_request(
        self,
        request_id: str,
        metrics_synced: int = 0
    ) -> Dict[str, Any]:
        """Mark a sync request as complete."""
        return await self._sync.complete_sync_request(request_id, metrics_synced)
    
    # =========================================
    # Blood Pressure & Heart Rate - Delegate to BloodPressureService
    # =========================================
    
    async def store_blood_pressure_reading(
        self,
        user_id: str,
        systolic: int,
        diastolic: int,
        pulse: Optional[int],
        timestamp: str,
        source: Optional[str] = None,
        crisis_flag: bool = False
    ) -> Dict[str, Any]:
        """Store a single blood pressure reading."""
        return await self._blood_pressure.store_blood_pressure_reading(
            user_id, systolic, diastolic, pulse, timestamp, source, crisis_flag
        )
    
    async def store_blood_pressure_batch(
        self,
        user_id: str,
        readings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Store multiple blood pressure readings."""
        return await self._blood_pressure.store_blood_pressure_batch(user_id, readings)
    
    async def get_patient_blood_pressure_history(
        self,
        patient_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get blood pressure history for a patient."""
        return await self._blood_pressure.get_patient_blood_pressure_history(patient_id, days)

    async def get_patient_blood_pressure_readings(
        self,
        patient_id: str,
        days: int = 30,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """Get raw individual BP readings for a patient (caregiver view)."""
        return await self._blood_pressure.get_patient_blood_pressure_readings(
            patient_id, days, limit
        )
    
    async def get_patient_heart_rate_history(
        self,
        patient_id: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get heart rate history for a patient."""
        return await self._blood_pressure.get_patient_heart_rate_history(patient_id, days)
