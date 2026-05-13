"""
Blood Pressure Service.

Handles blood pressure and heart rate data storage and history:
- Store single BP readings
- Store BP reading batches
- Retrieve BP history
- Retrieve HR history

Following Single Responsibility Principle (SRP).
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
from bson import ObjectId
from src._config.logger import get_logger
from src.domains.health.classification import classify_blood_pressure
from src.domains.health.adapters import extract_date_from_timestamp

logger = get_logger(__name__)


class BloodPressureService:
    """Service for blood pressure and heart rate data management."""
    
    def __init__(self, db):
        self.db = db
    
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
        
        result = await self.db.blood_pressure_readings.insert_one(doc)
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
            result = await self.db.blood_pressure_readings.insert_many(docs)
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
        cursor = self.db.blood_pressure_readings.find({
            "userId": patient_id,
            "date": {"$gte": start_date_str}
        })
        readings = await cursor.to_list(length=10000)
        
        # Group by date
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
