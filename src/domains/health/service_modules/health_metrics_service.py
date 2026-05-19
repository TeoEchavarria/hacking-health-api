"""
Health Metrics Service.

Handles health metrics ingestion from wearable devices:
- Steps tracking
- Sleep monitoring
- Heart rate aggregation
- HR sample storage

Following Single Responsibility Principle (SRP).
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta, date as date_type
from src._config.logger import get_logger

logger = get_logger(__name__)


class HealthMetricsService:
    """Service for health metrics ingestion and storage."""
    
    def __init__(self, db):
        self.db = db
    
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

    # -------------------------------------------------------------------------
    # Read-side: history queries (used by /caregiver/* endpoints)
    # -------------------------------------------------------------------------

    @staticmethod
    def _date_to_str(d) -> Optional[str]:
        if d is None:
            return None
        if isinstance(d, str):
            return d
        return d.isoformat()

    async def _get_typed_history(
        self,
        user_id: str,
        metric_type: str,
        date_from=None,
        date_to=None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Generic history loader for documents in health_metrics keyed by `type`.
        Filters by ISO date string (the `date` field).
        """
        query: Dict[str, Any] = {"userId": user_id, "type": metric_type}

        date_filter: Dict[str, Any] = {}
        df = self._date_to_str(date_from)
        dt = self._date_to_str(date_to)
        if df:
            date_filter["$gte"] = df
        if dt:
            date_filter["$lte"] = dt
        if date_filter:
            query["date"] = date_filter

        cursor = self.db.health_metrics.find(query).sort("date", -1).limit(int(limit))
        docs = await cursor.to_list(length=int(limit))

        results: List[Dict[str, Any]] = []
        for d in docs:
            results.append({
                "date": d.get("date"),
                "value": d.get("value"),
                "timestamp": d.get("timestamp"),
                "source": d.get("source"),
            })
        return results

    async def get_steps_history(
        self,
        user_id: str,
        date_from=None,
        date_to=None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """Return steps history (most recent first) for a patient."""
        records = await self._get_typed_history(
            user_id, "steps", date_from, date_to, limit
        )
        return {"user_id": user_id, "type": "steps", "records": records}

    async def get_sleep_history(
        self,
        user_id: str,
        date_from=None,
        date_to=None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """
        Return sleep history for a patient.
        `value` is total sleep in minutes (matches ingestion).
        """
        records = await self._get_typed_history(
            user_id, "sleep", date_from, date_to, limit
        )
        # Convenience: surface hours as well
        for r in records:
            mins = r.get("value")
            r["total_minutes"] = mins
            r["total_hours"] = round(mins / 60.0, 2) if isinstance(mins, (int, float)) else None
        return {"user_id": user_id, "type": "sleep", "records": records}

    async def get_30day_summary(self, user_id: str) -> Dict[str, Any]:
        """
        30-day aggregated summary for a patient.

        Aggregates:
          - blood_pressure: avg systolic/diastolic + reading count
            (queried from `blood_pressure_readings` collection)
          - steps: total + daily average
          - sleep: avg minutes/hours per day

        Date window: rolling 30 days based on UTC today.
        """
        now = datetime.now(timezone.utc)
        end_date = now.date()
        start_date = end_date - timedelta(days=30)
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        window_start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)

        # --- Blood pressure (from blood_pressure_readings) ---
        bp_pipeline = [
            {"$match": {
                "userId": user_id,
                "$or": [
                    {"date": {"$gte": start_str, "$lte": end_str}},
                    {"timestamp": {"$gte": window_start_dt.isoformat()}},
                ],
            }},
            {"$group": {
                "_id": None,
                "avg_systolic": {"$avg": "$systolic"},
                "avg_diastolic": {"$avg": "$diastolic"},
                "count": {"$sum": 1},
            }},
        ]
        bp_agg = await self.db.blood_pressure_readings.aggregate(bp_pipeline).to_list(length=1)
        bp_result = bp_agg[0] if bp_agg else None

        # --- Steps (from health_metrics) ---
        steps_pipeline = [
            {"$match": {
                "userId": user_id,
                "type": "steps",
                "date": {"$gte": start_str, "$lte": end_str},
            }},
            {"$group": {
                "_id": None,
                "total": {"$sum": "$value"},
                "days": {"$sum": 1},
                "average": {"$avg": "$value"},
            }},
        ]
        steps_agg = await self.db.health_metrics.aggregate(steps_pipeline).to_list(length=1)
        steps_result = steps_agg[0] if steps_agg else None

        # --- Sleep (from health_metrics, value in minutes) ---
        sleep_pipeline = [
            {"$match": {
                "userId": user_id,
                "type": "sleep",
                "date": {"$gte": start_str, "$lte": end_str},
            }},
            {"$group": {
                "_id": None,
                "avg_minutes": {"$avg": "$value"},
                "days": {"$sum": 1},
            }},
        ]
        sleep_agg = await self.db.health_metrics.aggregate(sleep_pipeline).to_list(length=1)
        sleep_result = sleep_agg[0] if sleep_agg else None

        avg_sleep_min = sleep_result["avg_minutes"] if sleep_result else None

        return {
            "user_id": user_id,
            "window": {"from": start_str, "to": end_str, "days": 30},
            "blood_pressure": {
                "avg_systolic": round(bp_result["avg_systolic"], 1) if bp_result and bp_result.get("avg_systolic") is not None else None,
                "avg_diastolic": round(bp_result["avg_diastolic"], 1) if bp_result and bp_result.get("avg_diastolic") is not None else None,
                "readings_count": bp_result["count"] if bp_result else 0,
            },
            "steps": {
                "total": int(steps_result["total"]) if steps_result and steps_result.get("total") is not None else 0,
                "daily_average": round(steps_result["average"], 0) if steps_result and steps_result.get("average") is not None else 0,
                "days_with_data": steps_result["days"] if steps_result else 0,
            },
            "sleep": {
                "avg_minutes": round(avg_sleep_min, 1) if avg_sleep_min is not None else None,
                "avg_hours": round(avg_sleep_min / 60.0, 2) if avg_sleep_min is not None else None,
                "days_with_data": sleep_result["days"] if sleep_result else 0,
            },
        }
