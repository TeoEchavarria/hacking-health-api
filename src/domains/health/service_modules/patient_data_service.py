"""
Patient Data Service.

Handles patient data queries and retrieval operations:
- Sensor data queries
- Patient alerts
- Health summaries
- Biometrics history

Following Single Responsibility Principle (SRP).
"""
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from src._config.logger import get_logger
from src.domains.health.adapters import normalize_timestamp, timestamp_to_ms
from src.domains.health.classification import classify_blood_pressure, classify_heart_rate

logger = get_logger(__name__)


class PatientDataService:
    """Service for patient data queries and retrieval."""
    
    def __init__(self, db):
        self.db = db
    
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
        
        # Fetch batches sorted by newest first
        cursor = self.db.sensor_batches.find(query).sort(
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
        db_cursor = self.db.alerts.find(query).sort(
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
                "last_reading_time": timestamp_to_ms(hr_data.get("timestamp")),
                "current_category": hr_category["category"]
            }
            response["data_available"] = True
            response["last_sync"] = timestamp_to_ms(hr_data.get("timestamp"))
        
        # Try to get blood pressure data
        bp_data = await self.db.blood_pressure_readings.find_one({
            "userId": patient_id,
            "timestamp": {"$gte": start_iso}
        }, sort=[("timestamp", -1)])
        
        if bp_data:
            # Count BP readings in last 24 hours
            bp_count = await self.db.blood_pressure_readings.count_documents({
                "userId": patient_id,
                "timestamp": {"$gte": start_iso}
            })
            
            # Get stats from last 24h readings
            bp_cursor = self.db.blood_pressure_readings.find({
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
                    "last_reading_time": timestamp_to_ms(latest["timestamp"]),
                    "current_stage": classification["stage"],
                    "reading_count": bp_count
                }
                response["data_available"] = True
                
                # Update last_sync if BP is more recent
                bp_ts_ms = timestamp_to_ms(latest["timestamp"])
                if not response["last_sync"] or (bp_ts_ms and bp_ts_ms > response["last_sync"]):
                    response["last_sync"] = bp_ts_ms
        
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
                "last_updated": timestamp_to_ms(steps_data.get("timestamp"))
            }
            response["data_available"] = True
            ts_ms = timestamp_to_ms(steps_data.get("timestamp"))
            if not response["last_sync"] or (ts_ms and ts_ms > response["last_sync"]):
                response["last_sync"] = ts_ms
        
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
                "last_updated": timestamp_to_ms(sleep_data.get("timestamp"))
            }
            response["data_available"] = True
            ts_ms = timestamp_to_ms(sleep_data.get("timestamp"))
            if not response["last_sync"] or (ts_ms and ts_ms > response["last_sync"]):
                response["last_sync"] = ts_ms
        
        # If no health_metrics data, check if there's any sensor_batches data
        if not response["data_available"]:
            latest_batch = await self.db.sensor_batches.find_one(
                {"userId": patient_id},
                sort=[("createdAt", -1)]
            )
            if latest_batch:
                response["last_sync"] = normalize_timestamp(
                    int(latest_batch["createdAt"].timestamp() * 1000)
                )
        
        return response
    
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
