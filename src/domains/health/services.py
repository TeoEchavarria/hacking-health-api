"""
Business logic for health domain.
Handles patient data access authorization and retrieval.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from bson import ObjectId
from src._config.logger import get_logger

logger = get_logger(__name__)

SENSOR_BATCHES_COLLECTION = "sensor_batches"
ALERTS_COLLECTION = "alerts"
PAIRINGS_COLLECTION = "pairings"


class HealthService:
    """Service for managing health data operations."""
    
    def __init__(self, db):
        self.db = db
    
    async def verify_patient_access(
        self, 
        requester_id: str, 
        patient_id: str
    ) -> bool:
        """
        Verify if requester has access to patient's data.
        
        Access is granted if:
        1. requester_id == patient_id (accessing own data)
        2. requester is an active caregiver for this patient
        
        Args:
            requester_id: ID of the user making the request
            patient_id: ID of the patient whose data is being accessed
            
        Returns:
            bool: True if access is allowed, False otherwise
        """
        # Case 1: User accessing their own data
        if requester_id == patient_id:
            logger.debug(f"User {requester_id} accessing own data")
            return True
        
        # Case 2: Check if requester is an active caregiver for this patient
        pairing = await self.db[PAIRINGS_COLLECTION].find_one({
            "caregiverId": requester_id,
            "patientId": patient_id,
            "status": "active"
        })
        
        if pairing:
            logger.debug(
                f"Caregiver {requester_id} has active pairing with patient {patient_id}"
            )
            return True
        
        logger.warning(
            f"Access denied: User {requester_id} attempted to access "
            f"data of patient {patient_id} without valid pairing"
        )
        return False
    
    async def get_patient_sensor_data(
        self,
        patient_id: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get sensor data for a patient.
        
        Args:
            patient_id: ID of the patient
            start_time: Start timestamp in ms (inclusive)
            end_time: End timestamp in ms (inclusive)
            limit: Maximum number of records to return
            
        Returns:
            Dict with patient_id, records, count, has_more, timestamps
        """
        # Build query
        query = {"userId": patient_id}
        
        # Time filtering is applied to records within batches
        # For now, fetch batches and flatten records
        
        # Fetch batches sorted by newest first
        cursor = self.db[SENSOR_BATCHES_COLLECTION].find(query).sort(
            "createdAt", -1
        ).limit(50)  # Limit batches to prevent memory issues
        
        batches = await cursor.to_list(length=50)
        
        # Flatten records from batches and apply time filters
        all_records = []
        for batch in batches:
            for record in batch.get("records", []):
                ts = record.get("timestamp", 0)
                
                # Apply time filters
                if start_time is not None and ts < start_time:
                    continue
                if end_time is not None and ts > end_time:
                    continue
                    
                all_records.append({
                    "timestamp": ts,
                    "x": record.get("x", 0),
                    "y": record.get("y", 0),
                    "z": record.get("z", 0)
                })
        
        # Sort by timestamp descending (newest first)
        all_records.sort(key=lambda r: r["timestamp"], reverse=True)
        
        # Apply limit
        has_more = len(all_records) > limit
        records = all_records[:limit]
        
        # Calculate timestamp range
        oldest_ts = records[-1]["timestamp"] if records else None
        newest_ts = records[0]["timestamp"] if records else None
        
        return {
            "patient_id": patient_id,
            "records": records,
            "count": len(records),
            "has_more": has_more,
            "oldest_timestamp": oldest_ts,
            "newest_timestamp": newest_ts
        }
    
    async def get_patient_alerts(
        self,
        patient_id: str,
        cursor: Optional[str] = None,
        limit: int = 50,
        severity: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get alerts for a patient.
        
        Args:
            patient_id: ID of the patient
            cursor: Pagination cursor (alert_id to start after)
            limit: Maximum number of alerts to return
            severity: Filter by severity level
            
        Returns:
            Dict with patient_id, alerts, count, next_cursor, has_more
        """
        # Build query
        query: Dict[str, Any] = {"patient_id": patient_id}
        
        if severity:
            query["severity"] = severity
        
        # Cursor-based pagination
        if cursor:
            try:
                query["_id"] = {"$lt": ObjectId(cursor)}
            except Exception:
                logger.warning(f"Invalid cursor format: {cursor}")
        
        # Fetch alerts sorted by newest first
        db_cursor = self.db[ALERTS_COLLECTION].find(query).sort(
            "_id", -1
        ).limit(limit + 1)  # +1 to check if there are more
        
        alerts_list = await db_cursor.to_list(length=limit + 1)
        
        # Check if there are more results
        has_more = len(alerts_list) > limit
        if has_more:
            alerts_list = alerts_list[:limit]
        
        # Format alerts for response
        formatted_alerts = []
        for alert in alerts_list:
            formatted_alerts.append({
                "alert_id": str(alert["_id"]),
                "type": alert.get("type", "unknown"),
                "severity": alert.get("severity", "info"),
                "status": alert.get("status", "pending"),
                "created_at": int(alert.get("created_at", datetime.now(timezone.utc)).timestamp() * 1000),
                "title": alert.get("title", ""),
                "body": alert.get("body", ""),
                "guidance": alert.get("guidance"),
                "cause": alert.get("cause")
            })
        
        # Calculate next cursor
        next_cursor = None
        if has_more and formatted_alerts:
            next_cursor = formatted_alerts[-1]["alert_id"]
        
        return {
            "patient_id": patient_id,
            "alerts": formatted_alerts,
            "count": len(formatted_alerts),
            "next_cursor": next_cursor,
            "has_more": has_more
        }
