"""
Business logic for health domain.
Handles patient data access authorization and retrieval.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from src._config.logger import get_logger
from src.domains.health.adapters import normalize_timestamp, extract_date_from_timestamp, now_iso
from src.domains.health.classification import classify_blood_pressure, classify_heart_rate

logger = get_logger(__name__)

SENSOR_BATCHES_COLLECTION = "sensor_batches"
ALERTS_COLLECTION = "alerts"
PAIRINGS_COLLECTION = "pairings"
BP_COLLECTION = "blood_pressure_readings"


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
            Dict with health metrics summary including blood pressure
        """
        # Get patient name
        user = await self.db.users.find_one({"_id": ObjectId(patient_id)})
        patient_name = user.get("name", "Usuario") if user else "Usuario"
        
        # Time range: last 24 hours
        now = datetime.now(timezone.utc)
        twenty_four_hours_ago = now - timedelta(hours=24)
        start_ts = int(twenty_four_hours_ago.timestamp() * 1000)
        start_iso = twenty_four_hours_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Initialize response with new structure
        response = {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "heart_rate": {"available": False},
            "blood_pressure": {"available": False, "reading_count": 0},
            "steps": {"available": False},
            "sleep": {"available": False},
            "last_sync": None,
            "data_available": False
        }
        
        # Try to get heart rate data from health_metrics collection
        hr_data = await self.db.health_metrics.find_one({
            "userId": patient_id,
            "type": "heart_rate",
            "timestamp": {"$gte": start_ts}
        }, sort=[("timestamp", -1)])
        
        if hr_data and hr_data.get("average"):
            hr_category = classify_heart_rate(hr_data.get("average"))
            response["heart_rate"] = {
                "available": True,
                "average": hr_data.get("average"),
                "min": hr_data.get("min"),
                "max": hr_data.get("max"),
                "last_reading": hr_data.get("average"),
                "last_reading_time": normalize_timestamp(hr_data.get("timestamp")),
                "current_category": hr_category["category"]
            }
            response["data_available"] = True
            response["last_sync"] = normalize_timestamp(hr_data.get("timestamp"))
        
        # Try to get blood pressure data
        bp_data = await self.db[BP_COLLECTION].find_one({
            "userId": patient_id,
            "timestamp": {"$gte": start_iso}
        }, sort=[("timestamp", -1)])
        
        if bp_data:
            # Count BP readings in last 24 hours
            bp_count = await self.db[BP_COLLECTION].count_documents({
                "userId": patient_id,
                "timestamp": {"$gte": start_iso}
            })
            
            # Get stats from last 24h readings
            bp_cursor = self.db[BP_COLLECTION].find({
                "userId": patient_id,
                "timestamp": {"$gte": start_iso}
            })
            bp_readings = await bp_cursor.to_list(length=100)
            
            if bp_readings:
                systolics = [r["systolic"] for r in bp_readings]
                diastolics = [r["diastolic"] for r in bp_readings]
                
                latest = bp_data
                classification = classify_blood_pressure(latest["systolic"], latest["diastolic"])
                
                response["blood_pressure"] = {
                    "available": True,
                    "avg_systolic": round(sum(systolics) / len(systolics)),
                    "avg_diastolic": round(sum(diastolics) / len(diastolics)),
                    "min_systolic": min(systolics),
                    "max_systolic": max(systolics),
                    "last_systolic": latest["systolic"],
                    "last_diastolic": latest["diastolic"],
                    "last_pulse": latest.get("pulse"),
                    "last_reading_time": latest["timestamp"],
                    "current_stage": classification["stage"],
                    "reading_count": bp_count
                }
                response["data_available"] = True
                
                # Update last_sync if BP is more recent
                if not response["last_sync"] or latest["timestamp"] > response["last_sync"]:
                    response["last_sync"] = latest["timestamp"]
        
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
                "last_updated": normalize_timestamp(steps_data.get("timestamp"))
            }
            response["data_available"] = True
            ts_iso = normalize_timestamp(steps_data.get("timestamp"))
            if not response["last_sync"] or (ts_iso and ts_iso > response["last_sync"]):
                response["last_sync"] = ts_iso
        
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
                "last_updated": normalize_timestamp(sleep_data.get("timestamp"))
            }
            response["data_available"] = True
            ts_iso = normalize_timestamp(sleep_data.get("timestamp"))
            if not response["last_sync"] or (ts_iso and ts_iso > response["last_sync"]):
                response["last_sync"] = ts_iso
        
        # If no health_metrics data, check if there's any sensor_batches data
        if not response["data_available"]:
            latest_batch = await self.db[SENSOR_BATCHES_COLLECTION].find_one(
                {"userId": patient_id},
                sort=[("createdAt", -1)]
            )
            if latest_batch:
                response["last_sync"] = normalize_timestamp(
                    int(latest_batch["createdAt"].timestamp() * 1000)
                )
        
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
        source = metrics.source or "unknown"  # Default if not provided
        
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
                        "source": source,
                        "updatedAt": now
                    },
                    "$setOnInsert": {
                        "createdAt": now
                    }
                },
                upsert=True
            )
            metrics_stored += 1
            logger.info(f"Stored steps for {metrics.user_id}: {metrics.steps} (source: {source})")
        
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
                        "source": source,
                        "updatedAt": now
                    },
                    "$setOnInsert": {
                        "createdAt": now
                    }
                },
                upsert=True
            )
            metrics_stored += 1
            logger.info(f"Stored sleep for {metrics.user_id}: {metrics.sleep_minutes} min (source: {source})")
        
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
                        "source": source,
                        "updatedAt": now
                    },
                    "$setOnInsert": {
                        "createdAt": now
                    }
                },
                upsert=True
            )
            metrics_stored += 1
            logger.info(f"Stored heart_rate for {metrics.user_id}: avg={metrics.avg_heart_rate} (source: {source})")
        
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
                    "source": source,
                    "createdAt": now
                }
                for sample in metrics.heart_rate_samples
            ]
            if hr_docs:
                await self.db.health_metrics.insert_many(hr_docs)
                metrics_stored += len(hr_docs)
                logger.info(f"Stored {len(hr_docs)} HR samples for {metrics.user_id} (source: {source})")
        
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
    
    # =========================================
    # Blood Pressure Methods
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
        """
        Store a single blood pressure reading.
        
        Args:
            user_id: User's ID
            systolic: Systolic BP in mmHg
            diastolic: Diastolic BP in mmHg
            pulse: Optional pulse reading in BPM
            timestamp: ISO 8601 timestamp
            source: Source of reading (e.g., "omron_ble", "manual")
            crisis_flag: Whether edge detected a crisis
            
        Returns:
            Dict with the stored reading document
        """
        # Classify the reading
        classification = classify_blood_pressure(systolic, diastolic)
        
        # Extract date for aggregation
        date = extract_date_from_timestamp(timestamp)
        
        # Create document
        now = datetime.now(timezone.utc)
        doc = {
            "userId": user_id,
            "systolic": systolic,
            "diastolic": diastolic,
            "pulse": pulse,
            "timestamp": timestamp,
            "date": date,
            "source": source,
            "stage": classification["stage"],
            "severity": classification["severity"],
            "crisis_flag": crisis_flag,
            "createdAt": now
        }
        
        result = await self.db[BP_COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id
        
        logger.info(
            f"Stored BP reading for {user_id}: {systolic}/{diastolic} "
            f"({classification['stage']})"
        )
        
        return doc
    
    async def store_blood_pressure_batch(
        self,
        user_id: str,
        readings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Store multiple blood pressure readings.
        
        Args:
            user_id: User's ID
            readings: List of BP reading dicts with systolic, diastolic, pulse, timestamp, source
            
        Returns:
            Dict with stored_count and list of stored documents
        """
        now = datetime.now(timezone.utc)
        docs = []
        
        for reading in readings:
            classification = classify_blood_pressure(
                reading["systolic"], reading["diastolic"]
            )
            date = extract_date_from_timestamp(reading["timestamp"])
            
            docs.append({
                "userId": user_id,
                "systolic": reading["systolic"],
                "diastolic": reading["diastolic"],
                "pulse": reading.get("pulse"),
                "timestamp": reading["timestamp"],
                "date": date,
                "source": reading.get("source"),
                "stage": classification["stage"],
                "severity": classification["severity"],
                "crisis_flag": False,
                "createdAt": now
            })
        
        if docs:
            result = await self.db[BP_COLLECTION].insert_many(docs)
            for i, doc in enumerate(docs):
                doc["_id"] = result.inserted_ids[i]
        
        logger.info(f"Stored {len(docs)} BP readings for {user_id}")
        
        return {
            "stored_count": len(docs),
            "documents": docs
        }
    
    async def get_patient_blood_pressure_history(
        self,
        patient_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get blood pressure history for a patient.
        
        Args:
            patient_id: ID of the patient
            days: Number of days of history to retrieve
            
        Returns:
            Dict with patient_id, patient_name, days_requested, data_points, count
        """
        # Get patient name
        user = await self.db.users.find_one({"_id": ObjectId(patient_id)})
        patient_name = user.get("name", "Usuario") if user else "Usuario"
        
        # Calculate date range
        today = datetime.now(timezone.utc).date()
        start_date = today - timedelta(days=days - 1)
        start_date_str = start_date.isoformat()
        
        # Query all BP readings in date range
        cursor = self.db[BP_COLLECTION].find({
            "userId": patient_id,
            "date": {"$gte": start_date_str}
        })
        readings = await cursor.to_list(length=10000)
        
        # Group by date
        from collections import defaultdict
        by_date = defaultdict(list)
        for r in readings:
            by_date[r["date"]].append(r)
        
        # Build data points
        data_points = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            date_str = date.isoformat()
            day_readings = by_date.get(date_str, [])
            
            if day_readings:
                systolics = [r["systolic"] for r in day_readings]
                diastolics = [r["diastolic"] for r in day_readings]
                pulses = [r["pulse"] for r in day_readings if r.get("pulse")]
                stages = [r["stage"] for r in day_readings]
                
                # Determine dominant stage (most frequent)
                from collections import Counter
                stage_counts = Counter(stages)
                dominant_stage = stage_counts.most_common(1)[0][0] if stage_counts else None
                
                data_points.append({
                    "date": date_str,
                    "avg_systolic": round(sum(systolics) / len(systolics)),
                    "avg_diastolic": round(sum(diastolics) / len(diastolics)),
                    "min_systolic": min(systolics),
                    "max_systolic": max(systolics),
                    "avg_pulse": round(sum(pulses) / len(pulses)) if pulses else None,
                    "stage": dominant_stage,
                    "sample_count": len(day_readings)
                })
            else:
                data_points.append({
                    "date": date_str,
                    "avg_systolic": None,
                    "avg_diastolic": None,
                    "min_systolic": None,
                    "max_systolic": None,
                    "avg_pulse": None,
                    "stage": None,
                    "sample_count": 0
                })
        
        return {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "days_requested": days,
            "data_points": data_points,
            "count": len([dp for dp in data_points if dp["avg_systolic"] is not None])
        }

    # =========================================
    # Biometrics History (Unified GET)
    # =========================================
    
    async def get_biometrics_history(
        self,
        user_id: str,
        limit: int = 50,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get biometric history for a user.
        
        Returns:
            Dict with isEmpty flag, latest values, and full history.
            Returns empty list (not 404) for new users.
        """
        from src.utils.formatters import format_sleep_duration
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Fetch all metrics for user within date range
        cursor = self.db.health_metrics.find({
            "userId": user_id,
            "timestamp": {"$gte": cutoff_iso}
        }).sort("timestamp", -1).limit(limit)
        
        records = await cursor.to_list(length=limit)
        
        # If no records, user is new or has no data
        if not records:
            return {
                "isEmpty": True,
                "latest": None,
                "history": [],
                "count": 0
            }
        
        # Extract latest of each type
        latest_hr = next((r for r in records if r.get("type") == "heart_rate"), None)
        latest_steps = next((r for r in records if r.get("type") == "steps"), None)
        latest_sleep = next((r for r in records if r.get("type") == "sleep"), None)
        
        sleep_minutes = latest_sleep.get("value") if latest_sleep else None
        
        latest = {
            "heartRate": latest_hr.get("average") if latest_hr else None,
            "heartRateMin": latest_hr.get("min") if latest_hr else None,
            "heartRateMax": latest_hr.get("max") if latest_hr else None,
            "steps": latest_steps.get("value") if latest_steps else None,
            "sleepMinutes": sleep_minutes,
            "sleepFormatted": format_sleep_duration(sleep_minutes) if sleep_minutes is not None else None,
        }
        
        # Format history for response
        history = [
            {
                "id": str(r.get("_id")),
                "type": r.get("type"),
                "value": r.get("value") if r.get("value") is not None else r.get("average"),
                "date": r.get("date"),
                "timestamp": r.get("timestamp"),
                "source": r.get("source", "unknown"),
            }
            for r in records
        ]
        
        return {
            "isEmpty": False,
            "latest": latest,
            "history": history,
            "count": len(history)
        }
