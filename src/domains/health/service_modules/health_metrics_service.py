"""
Health Metrics Service.

Handles health metrics ingestion from wearable devices:
- Steps tracking
- Sleep monitoring
- Heart rate aggregation
- HR sample storage

Following Single Responsibility Principle (SRP).
"""
from typing import Dict, Any
from datetime import datetime, timezone
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
