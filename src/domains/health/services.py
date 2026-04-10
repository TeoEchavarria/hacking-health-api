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

    async def get_patient_health_summary(
        self,
        patient_id: str
    ) -> Dict[str, Any]:
        """
        Get health summary for a patient (last 24 hours).
        
        Args:
            patient_id: ID of the patient
            
        Returns:
            Dict with health metrics summary
        """
        from datetime import timedelta
        
        # Get patient name
        user = await self.db.users.find_one({"_id": ObjectId(patient_id)})
        patient_name = user.get("name", "Usuario") if user else "Usuario"
        
        # Time range: last 24 hours
        now = datetime.now(timezone.utc)
        twenty_four_hours_ago = now - timedelta(hours=24)
        start_ts = int(twenty_four_hours_ago.timestamp() * 1000)
        
        # Initialize response
        response = {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "heart_rate": {"available": False},
            "steps": {"available": False},
            "sleep": {"available": False},
            "unavailable_metrics": [
                {"name": "SpO2", "reason": "NO DISPONIBLE PARA TU DISPOSITIVO"},
                {"name": "Presión Arterial", "reason": "NO DISPONIBLE PARA TU DISPOSITIVO"},
                {"name": "Temperatura", "reason": "NO DISPONIBLE PARA TU DISPOSITIVO"}
            ],
            "last_sync": None,
            "data_available": False
        }
        
        # Try to get heart rate data from health_metrics collection
        # Use find_one to get only the most recent heart rate record (more efficient)
        hr_data = await self.db.health_metrics.find_one({
            "userId": patient_id,
            "type": "heart_rate",
            "timestamp": {"$gte": start_ts}
        }, sort=[("timestamp", -1)])
        
        if hr_data and hr_data.get("average"):
            # Use pre-aggregated values stored when data was synced from watch
            response["heart_rate"] = {
                "available": True,
                "average": hr_data.get("average"),
                "min": hr_data.get("min"),
                "max": hr_data.get("max"),
                "last_reading": hr_data.get("average"),
                "last_reading_time": hr_data.get("timestamp")
            }
            response["data_available"] = True
            response["last_sync"] = hr_data.get("timestamp")
        
        # Try to get steps data
        steps_data = await self.db.health_metrics.find_one({
            "userId": patient_id,
            "type": "steps",
            "timestamp": {"$gte": start_ts}
        }, sort=[("timestamp", -1)])
        
        if steps_data:
            response["steps"] = {
                "available": True,
                "total": steps_data.get("value", 0),
                "last_updated": steps_data.get("timestamp")
            }
            response["data_available"] = True
            if not response["last_sync"] or steps_data.get("timestamp", 0) > response["last_sync"]:
                response["last_sync"] = steps_data.get("timestamp")
        
        # Try to get sleep data
        sleep_data = await self.db.health_metrics.find_one({
            "userId": patient_id,
            "type": "sleep",
            "timestamp": {"$gte": start_ts}
        }, sort=[("timestamp", -1)])
        
        if sleep_data:
            response["sleep"] = {
                "available": True,
                "total_minutes": sleep_data.get("value", 0),
                "last_night": sleep_data.get("value", 0),
                "last_updated": sleep_data.get("timestamp")
            }
            response["data_available"] = True
            if not response["last_sync"] or sleep_data.get("timestamp", 0) > response["last_sync"]:
                response["last_sync"] = sleep_data.get("timestamp")
        
        # If no health_metrics data, check if there's any sensor_batches data
        # to at least know the user has synced something
        if not response["data_available"]:
            latest_batch = await self.db[SENSOR_BATCHES_COLLECTION].find_one(
                {"userId": patient_id},
                sort=[("createdAt", -1)]
            )
            if latest_batch:
                response["last_sync"] = int(latest_batch["createdAt"].timestamp() * 1000)
        
        return response
    
    async def ingest_health_metrics(self, metrics) -> Dict[str, Any]:
        """
        Ingest health metrics from watch (via phone).
        Stores in health_metrics collection.
        
        Args:
            metrics: HealthMetricsInput with steps, sleep, heart_rate data
            
        Returns:
            Dict with success, message, metrics_stored count
        """
        metrics_stored = 0
        now = datetime.now(timezone.utc)
        
        # Store steps
        if metrics.steps is not None:
            await self.db.health_metrics.update_one(
                {
                    "userId": metrics.user_id,
                    "type": "steps",
                    "date": metrics.date
                },
                {
                    "$set": {
                        "value": metrics.steps,
                        "timestamp": metrics.sync_timestamp,
                        "updatedAt": now
                    },
                    "$setOnInsert": {
                        "createdAt": now
                    }
                },
                upsert=True
            )
            metrics_stored += 1
            logger.info(f"Stored steps for {metrics.user_id}: {metrics.steps}")
        
        # Store sleep
        if metrics.sleep_minutes is not None:
            await self.db.health_metrics.update_one(
                {
                    "userId": metrics.user_id,
                    "type": "sleep",
                    "date": metrics.date
                },
                {
                    "$set": {
                        "value": metrics.sleep_minutes,
                        "timestamp": metrics.sync_timestamp,
                        "updatedAt": now
                    },
                    "$setOnInsert": {
                        "createdAt": now
                    }
                },
                upsert=True
            )
            metrics_stored += 1
            logger.info(f"Stored sleep for {metrics.user_id}: {metrics.sleep_minutes} min")
        
        # Store heart rate (latest aggregated values)
        if metrics.avg_heart_rate is not None:
            await self.db.health_metrics.update_one(
                {
                    "userId": metrics.user_id,
                    "type": "heart_rate",
                    "date": metrics.date
                },
                {
                    "$set": {
                        "average": metrics.avg_heart_rate,
                        "min": metrics.min_heart_rate,
                        "max": metrics.max_heart_rate,
                        "timestamp": metrics.sync_timestamp,
                        "updatedAt": now
                    },
                    "$setOnInsert": {
                        "createdAt": now
                    }
                },
                upsert=True
            )
            metrics_stored += 1
            logger.info(f"Stored heart_rate for {metrics.user_id}: avg={metrics.avg_heart_rate}")
        
        # Store individual HR samples if provided
        if metrics.heart_rate_samples:
            hr_docs = [
                {
                    "userId": metrics.user_id,
                    "type": "heart_rate_sample",
                    "date": metrics.date,
                    "bpm": sample.bpm,
                    "timestamp": sample.timestamp,
                    "accuracy": sample.accuracy,
                    "createdAt": now
                }
                for sample in metrics.heart_rate_samples
            ]
            if hr_docs:
                await self.db.health_metrics.insert_many(hr_docs)
                metrics_stored += len(hr_docs)
                logger.info(f"Stored {len(hr_docs)} HR samples for {metrics.user_id}")
        
        return {
            "success": True,
            "message": "Métricas guardadas correctamente",
            "metrics_stored": metrics_stored
        }
    
    # =========================================
    # Sync Request Methods (On-Demand Sync)
    # =========================================
    
    async def create_sync_request(
        self,
        patient_id: str,
        requested_by: str,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """
        Create a sync request for a patient.
        Called by caregiver to request immediate sync.
        
        Args:
            patient_id: ID of the patient to sync
            requested_by: ID of the caregiver requesting sync
            priority: Request priority (normal|urgent)
            
        Returns:
            Dict with request_id, patient_id, requested_by, status, created_at
        """
        now = datetime.now(timezone.utc)
        request_doc = {
            "patient_id": patient_id,
            "requested_by": requested_by,
            "priority": priority,
            "status": "pending",
            "created_at": now,
            "completed_at": None
        }
        
        result = await self.db.sync_requests.insert_one(request_doc)
        
        logger.info(
            f"Sync request created: {result.inserted_id} "
            f"for patient {patient_id} by {requested_by}"
        )
        
        return {
            "request_id": str(result.inserted_id),
            "patient_id": patient_id,
            "requested_by": requested_by,
            "status": "pending",
            "created_at": int(now.timestamp() * 1000)
        }
    
    async def get_pending_sync_request(
        self,
        patient_id: str
    ) -> Dict[str, Any]:
        """
        Get the oldest pending sync request for a patient.
        Called by patient's device to check if sync is needed.
        
        Args:
            patient_id: ID of the patient
            
        Returns:
            Dict with has_pending, request_id, requested_by, priority, created_at
        """
        # Find oldest pending request
        request = await self.db.sync_requests.find_one(
            {
                "patient_id": patient_id,
                "status": "pending"
            },
            sort=[("created_at", 1)]  # FIFO - oldest first
        )
        
        if not request:
            return {"has_pending": False}
        
        return {
            "has_pending": True,
            "request_id": str(request["_id"]),
            "requested_by": request.get("requested_by"),
            "priority": request.get("priority", "normal"),
            "created_at": int(request["created_at"].timestamp() * 1000)
        }
    
    async def complete_sync_request(
        self,
        request_id: str,
        metrics_synced: int = 0
    ) -> Dict[str, Any]:
        """
        Mark a sync request as complete.
        Called by patient's device after syncing.
        
        Args:
            request_id: ID of the sync request
            metrics_synced: Number of metrics synced
            
        Returns:
            Dict with success, message
        """
        now = datetime.now(timezone.utc)
        
        result = await self.db.sync_requests.update_one(
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": now,
                    "metrics_synced": metrics_synced
                }
            }
        )
        
        if result.modified_count == 0:
            return {
                "success": False,
                "message": "Solicitud de sync no encontrada"
            }
        
        logger.info(f"Sync request {request_id} completed with {metrics_synced} metrics")
        
        return {
            "success": True,
            "message": "Sincronización completada"
        }
    
    # =========================================
    # Heart Rate History Methods
    # =========================================
    
    async def get_patient_heart_rate_history(
        self,
        patient_id: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get heart rate history for a patient.
        
        Args:
            patient_id: ID of the patient
            days: Number of days of history to retrieve
            
        Returns:
            Dict with patient_id, patient_name, days_requested, data_points, count
        """
        from datetime import timedelta
        
        # Get patient name
        user = await self.db.users.find_one({"_id": ObjectId(patient_id)})
        patient_name = user.get("name", "Usuario") if user else "Usuario"
        
        # Calculate date range
        today = datetime.now(timezone.utc).date()
        start_date = today - timedelta(days=days - 1)
        
        # Query heart rate records for each day
        data_points = []
        
        for i in range(days):
            date = start_date + timedelta(days=i)
            date_str = date.isoformat()
            
            # Get aggregated heart rate for this date
            hr_record = await self.db.health_metrics.find_one({
                "userId": patient_id,
                "type": "heart_rate",
                "date": date_str
            })
            
            # Count samples for this date
            sample_count = await self.db.health_metrics.count_documents({
                "userId": patient_id,
                "type": "heart_rate_sample",
                "date": date_str
            })
            
            data_points.append({
                "date": date_str,
                "avg_bpm": hr_record.get("average") if hr_record else None,
                "min_bpm": hr_record.get("min") if hr_record else None,
                "max_bpm": hr_record.get("max") if hr_record else None,
                "sample_count": sample_count
            })
        
        return {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "days_requested": days,
            "data_points": data_points,
            "count": len([dp for dp in data_points if dp["avg_bpm"] is not None])
        }
