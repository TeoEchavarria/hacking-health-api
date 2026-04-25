"""
Real-time analysis pipeline for blood pressure monitoring.

This module implements the analysis steps that run asynchronously
after each BP reading is stored:

Step 1: Store reading (happens synchronously in route handler)
Step 2: Compute rolling statistics (30-day window, min 3 readings)
Step 3: Z-score anomaly detection (|z| > 2.5, IQR for n < 15)
Step 4: CUSUM drift detection (detect +10mmHg shift)
Step 5: Trend detection (7-day SMA comparison)
Step 6: Persistence check (last 3 readings same stage)

Steps 2-6 run as FastAPI BackgroundTasks after the HTTP response.
"""
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from statistics import mean, stdev
import math

from src._config.logger import get_logger
from src.domains.health.classification import classify_blood_pressure
from src.domains.health.alert_generator import AlertGenerator
from src.domains.health.adapters import days_ago_iso, now_iso

logger = get_logger(__name__)

BP_COLLECTION = "blood_pressure_readings"
CUSUM_COLLECTION = "bp_cusum_state"

# Pipeline configuration
CONFIG = {
    "rolling_window_days": 30,
    "min_readings_for_stats": 3,
    "min_readings_for_zscore": 3,
    "iqr_threshold_n": 15,  # Use IQR instead of z-score when n < this
    "zscore_threshold": 2.5,
    "iqr_multiplier": 1.5,
    "cusum_slack": 5,  # mmHg acceptable natural variation
    "cusum_threshold": 20,  # trigger alert when exceeded
    "cusum_target_shift": 10,  # detect +10mmHg shift from baseline
    "cusum_min_readings": 7,
    "trend_min_days": 7,
    "trend_threshold": 5,  # mmHg increase week-over-week
    "persistence_count": 3  # number of consecutive readings to check
}


class BloodPressurePipeline:
    """
    Implements the BP analysis pipeline.
    
    Each method returns a dict with:
        - triggered: bool - whether an alert condition was met
        - alert_type: str or None - type of alert if triggered
        - details: dict - additional analysis details
    """
    
    def __init__(self, db):
        self.db = db
        self.alert_generator = AlertGenerator(db)
    
    async def run_full_pipeline(
        self,
        user_id: str,
        reading: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run the complete analysis pipeline for a new BP reading.
        
        This is the main entry point called by BackgroundTasks.
        
        Args:
            user_id: User's ID
            reading: The newly stored BP reading document
            
        Returns:
            Dict with pipeline results and any generated alerts
        """
        results = {
            "user_id": user_id,
            "reading_id": str(reading.get("_id")),
            "steps_run": [],
            "alerts_generated": []
        }
        
        systolic = reading["systolic"]
        diastolic = reading["diastolic"]
        
        # Step 2: Compute rolling statistics
        stats = await self.compute_rolling_stats(user_id)
        results["steps_run"].append({"step": 2, "name": "rolling_stats", "result": stats})
        
        if not stats["sufficient_data"]:
            logger.debug(f"Insufficient data for analysis pipeline (n={stats.get('count', 0)})")
            results["skipped_reason"] = "insufficient_data"
            return results
        
        # Step 3: Z-score anomaly detection
        anomaly = await self.detect_anomaly(
            user_id, systolic, diastolic, stats
        )
        results["steps_run"].append({"step": 3, "name": "anomaly_detection", "result": anomaly})
        
        if anomaly["triggered"]:
            alert = await self.alert_generator.generate_anomaly_alert(
                user_id=user_id,
                systolic=systolic,
                diastolic=diastolic,
                z_systolic=anomaly["details"].get("z_systolic", 0),
                z_diastolic=anomaly["details"].get("z_diastolic", 0)
            )
            if alert:
                results["alerts_generated"].append(alert["alert_id"])
        
        # Step 4: CUSUM drift detection
        drift = await self.detect_drift(user_id, systolic, stats)
        results["steps_run"].append({"step": 4, "name": "drift_detection", "result": drift})
        
        if drift["triggered"]:
            alert = await self.alert_generator.generate_drift_alert(
                user_id=user_id,
                cusum_value=drift["details"].get("cusum_pos", 0),
                baseline=stats["avg_systolic"]
            )
            if alert:
                results["alerts_generated"].append(alert["alert_id"])
        
        # Step 5: Trend detection
        trend = await self.detect_trend(user_id)
        results["steps_run"].append({"step": 5, "name": "trend_detection", "result": trend})
        
        if trend["triggered"]:
            alert = await self.alert_generator.generate_trend_alert(
                user_id=user_id,
                delta=trend["details"]["delta"],
                current_avg=trend["details"]["current_avg"],
                previous_avg=trend["details"]["previous_avg"]
            )
            if alert:
                results["alerts_generated"].append(alert["alert_id"])
        
        # Step 6: Persistence check
        persistence = await self.check_persistence(user_id)
        results["steps_run"].append({"step": 6, "name": "persistence_check", "result": persistence})
        
        if persistence["triggered"]:
            # Get last 3 readings for the alert
            recent = await self._get_recent_readings(user_id, limit=3)
            readings_list = [
                {"systolic": r["systolic"], "diastolic": r["diastolic"]}
                for r in recent
            ]
            alert = await self.alert_generator.generate_persistent_stage_alert(
                user_id=user_id,
                stage=persistence["details"]["stage"],
                readings=readings_list
            )
            if alert:
                results["alerts_generated"].append(alert["alert_id"])
        
        logger.info(
            f"Pipeline complete for user {user_id}: "
            f"{len(results['alerts_generated'])} alerts generated"
        )
        return results
    
    async def compute_rolling_stats(
        self,
        user_id: str,
        days: int = None
    ) -> Dict[str, Any]:
        """
        Step 2: Compute rolling statistics from the last N days.
        
        Args:
            user_id: User's ID
            days: Number of days to look back (default from CONFIG)
            
        Returns:
            Dict with avg, std, min, max for systolic and diastolic
        """
        days = days or CONFIG["rolling_window_days"]
        cutoff = days_ago_iso(days)
        
        # Fetch readings from last N days
        cursor = self.db[BP_COLLECTION].find({
            "userId": user_id,
            "timestamp": {"$gte": cutoff}
        }).sort("timestamp", -1)
        
        readings = await cursor.to_list(length=1000)
        
        if len(readings) < CONFIG["min_readings_for_stats"]:
            return {
                "sufficient_data": False,
                "count": len(readings),
                "min_required": CONFIG["min_readings_for_stats"]
            }
        
        systolics = [r["systolic"] for r in readings]
        diastolics = [r["diastolic"] for r in readings]
        
        result = {
            "sufficient_data": True,
            "count": len(readings),
            "days": days,
            "avg_systolic": mean(systolics),
            "avg_diastolic": mean(diastolics),
            "min_systolic": min(systolics),
            "max_systolic": max(systolics),
            "min_diastolic": min(diastolics),
            "max_diastolic": max(diastolics)
        }
        
        # Standard deviation (only if n >= 2)
        if len(readings) >= 2:
            result["std_systolic"] = stdev(systolics)
            result["std_diastolic"] = stdev(diastolics)
        else:
            result["std_systolic"] = 0
            result["std_diastolic"] = 0
        
        return result
    
    async def detect_anomaly(
        self,
        user_id: str,
        systolic: int,
        diastolic: int,
        stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Step 3: Z-score anomaly detection against personal baseline.
        
        Uses IQR method when n < 15 readings (more robust for small samples).
        
        Args:
            user_id: User's ID
            systolic: Current systolic BP
            diastolic: Current diastolic BP
            stats: Rolling statistics from step 2
            
        Returns:
            Dict with triggered flag and z-scores
        """
        count = stats.get("count", 0)
        
        if count < CONFIG["min_readings_for_zscore"]:
            return {
                "triggered": False,
                "method": None,
                "details": {"reason": "insufficient_data"}
            }
        
        # Choose method based on sample size
        if count < CONFIG["iqr_threshold_n"]:
            return await self._detect_anomaly_iqr(user_id, systolic, diastolic)
        else:
            return self._detect_anomaly_zscore(systolic, diastolic, stats)
    
    def _detect_anomaly_zscore(
        self,
        systolic: int,
        diastolic: int,
        stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Z-score based anomaly detection."""
        std_sys = stats.get("std_systolic", 0)
        std_dia = stats.get("std_diastolic", 0)
        
        # Avoid division by zero
        if std_sys == 0 or std_dia == 0:
            return {
                "triggered": False,
                "method": "zscore",
                "details": {"reason": "zero_std"}
            }
        
        z_systolic = (systolic - stats["avg_systolic"]) / std_sys
        z_diastolic = (diastolic - stats["avg_diastolic"]) / std_dia
        
        triggered = (
            abs(z_systolic) > CONFIG["zscore_threshold"] or
            abs(z_diastolic) > CONFIG["zscore_threshold"]
        )
        
        return {
            "triggered": triggered,
            "method": "zscore",
            "details": {
                "z_systolic": z_systolic,
                "z_diastolic": z_diastolic,
                "threshold": CONFIG["zscore_threshold"]
            }
        }
    
    async def _detect_anomaly_iqr(
        self,
        user_id: str,
        systolic: int,
        diastolic: int
    ) -> Dict[str, Any]:
        """IQR-based anomaly detection for small samples."""
        cutoff = days_ago_iso(CONFIG["rolling_window_days"])
        
        cursor = self.db[BP_COLLECTION].find({
            "userId": user_id,
            "timestamp": {"$gte": cutoff}
        })
        readings = await cursor.to_list(length=1000)
        
        if len(readings) < CONFIG["min_readings_for_zscore"]:
            return {
                "triggered": False,
                "method": "iqr",
                "details": {"reason": "insufficient_data"}
            }
        
        # Calculate IQR for systolic
        systolics = sorted([r["systolic"] for r in readings])
        diastolics = sorted([r["diastolic"] for r in readings])
        
        def calculate_iqr_bounds(values: List[int]) -> Tuple[float, float]:
            n = len(values)
            q1_idx = n // 4
            q3_idx = (3 * n) // 4
            q1 = values[q1_idx]
            q3 = values[q3_idx]
            iqr = q3 - q1
            lower = q1 - CONFIG["iqr_multiplier"] * iqr
            upper = q3 + CONFIG["iqr_multiplier"] * iqr
            return lower, upper
        
        sys_lower, sys_upper = calculate_iqr_bounds(systolics)
        dia_lower, dia_upper = calculate_iqr_bounds(diastolics)
        
        is_sys_anomaly = systolic < sys_lower or systolic > sys_upper
        is_dia_anomaly = diastolic < dia_lower or diastolic > dia_upper
        
        return {
            "triggered": is_sys_anomaly or is_dia_anomaly,
            "method": "iqr",
            "details": {
                "systolic_bounds": [sys_lower, sys_upper],
                "diastolic_bounds": [dia_lower, dia_upper],
                "is_systolic_anomaly": is_sys_anomaly,
                "is_diastolic_anomaly": is_dia_anomaly
            }
        }
    
    async def detect_drift(
        self,
        user_id: str,
        systolic: int,
        stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Step 4: CUSUM drift detection for gradual baseline shift.
        
        Maintains cumulative sum to detect when systolic has drifted
        +10 mmHg from baseline over time.
        
        cusum_pos = max(0, cusum_prev + (current - target) - slack)
        
        Args:
            user_id: User's ID
            systolic: Current systolic BP
            stats: Rolling statistics from step 2
            
        Returns:
            Dict with triggered flag and CUSUM details
        """
        count = stats.get("count", 0)
        
        if count < CONFIG["cusum_min_readings"]:
            return {
                "triggered": False,
                "details": {"reason": "insufficient_data", "count": count}
            }
        
        target = stats["avg_systolic"]
        
        # Get or initialize CUSUM state
        state = await self.db[CUSUM_COLLECTION].find_one({"userId": user_id})
        
        if state is None:
            cusum_prev = 0.0
        else:
            cusum_prev = state.get("cusum_pos", 0.0)
        
        # Update CUSUM
        # Target shift is +10 mmHg, so we look for readings above (target + shift/2)
        # This centers the CUSUM around detecting a shift of +10
        shift_target = target + (CONFIG["cusum_target_shift"] / 2)
        cusum_pos = max(0, cusum_prev + (systolic - shift_target) - CONFIG["cusum_slack"])
        
        # Store updated state
        await self.db[CUSUM_COLLECTION].update_one(
            {"userId": user_id},
            {
                "$set": {
                    "cusum_pos": cusum_pos,
                    "baseline": target,
                    "last_updated": now_iso()
                }
            },
            upsert=True
        )
        
        triggered = cusum_pos > CONFIG["cusum_threshold"]
        
        # Reset CUSUM if triggered (to allow future detections)
        if triggered:
            await self.db[CUSUM_COLLECTION].update_one(
                {"userId": user_id},
                {"$set": {"cusum_pos": 0}}
            )
        
        return {
            "triggered": triggered,
            "details": {
                "cusum_pos": cusum_pos,
                "cusum_prev": cusum_prev,
                "threshold": CONFIG["cusum_threshold"],
                "baseline": target
            }
        }
    
    async def detect_trend(self, user_id: str) -> Dict[str, Any]:
        """
        Step 5: Weekly trend detection.
        
        Compares 7-day simple moving average vs previous 7-day average.
        Triggers if systolic trend > +5 mmHg week-over-week.
        
        Requires 7+ readings spread across at least 2 weeks.
        
        Args:
            user_id: User's ID
            
        Returns:
            Dict with triggered flag and trend details
        """
        # Get readings from last 14 days, grouped by week
        cutoff_14d = days_ago_iso(14)
        cutoff_7d = days_ago_iso(7)
        
        cursor = self.db[BP_COLLECTION].find({
            "userId": user_id,
            "timestamp": {"$gte": cutoff_14d}
        })
        readings = await cursor.to_list(length=1000)
        
        if len(readings) < CONFIG["trend_min_days"]:
            return {
                "triggered": False,
                "details": {"reason": "insufficient_data", "count": len(readings)}
            }
        
        # Split into current week and previous week
        current_week = []
        previous_week = []
        
        for r in readings:
            ts = r["timestamp"]
            if ts >= cutoff_7d:
                current_week.append(r["systolic"])
            else:
                previous_week.append(r["systolic"])
        
        # Need data in both weeks
        if not current_week or not previous_week:
            return {
                "triggered": False,
                "details": {
                    "reason": "no_comparison_data",
                    "current_week_count": len(current_week),
                    "previous_week_count": len(previous_week)
                }
            }
        
        current_avg = mean(current_week)
        previous_avg = mean(previous_week)
        delta = current_avg - previous_avg
        
        triggered = delta > CONFIG["trend_threshold"]
        
        return {
            "triggered": triggered,
            "details": {
                "current_avg": round(current_avg),
                "previous_avg": round(previous_avg),
                "delta": round(delta),
                "threshold": CONFIG["trend_threshold"],
                "current_week_count": len(current_week),
                "previous_week_count": len(previous_week)
            }
        }
    
    async def check_persistence(self, user_id: str) -> Dict[str, Any]:
        """
        Step 6: Consecutive stage persistence check.
        
        Checks if last 3 readings are all the same hypertension stage.
        
        Args:
            user_id: User's ID
            
        Returns:
            Dict with triggered flag and persistence details
        """
        readings = await self._get_recent_readings(
            user_id, limit=CONFIG["persistence_count"]
        )
        
        if len(readings) < CONFIG["persistence_count"]:
            return {
                "triggered": False,
                "details": {"reason": "insufficient_readings", "count": len(readings)}
            }
        
        # Classify each reading
        stages = []
        for r in readings:
            classification = classify_blood_pressure(r["systolic"], r["diastolic"])
            stages.append(classification["stage"])
        
        # Check if all stages are the same and concerning
        unique_stages = set(stages)
        
        if len(unique_stages) == 1:
            stage = stages[0]
            if stage in ["hypertension_stage_2", "hypertension_stage_1"]:
                return {
                    "triggered": True,
                    "details": {
                        "stage": stage,
                        "count": len(readings),
                        "stages": stages
                    }
                }
        
        return {
            "triggered": False,
            "details": {
                "stages": stages,
                "reason": "no_persistent_pattern"
            }
        }
    
    async def _get_recent_readings(
        self,
        user_id: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Get the most recent BP readings for a user."""
        cursor = self.db[BP_COLLECTION].find({
            "userId": user_id
        }).sort("timestamp", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
