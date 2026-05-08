"""
Alert generation for blood pressure and heart rate monitoring.

This module handles alert creation with:
- Message template rendering
- 24-hour deduplication (except for hypertensive crisis)
- Proper guidance generation
- Push notifications to patient and caregivers

Alerts are stored in the existing 'alerts' collection.
"""
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import uuid

from src._config.logger import get_logger
from src.domains.health.adapters import now_iso
from src.utils.fcm_client import send_health_alert_push, is_fcm_available

logger = get_logger(__name__)

ALERTS_COLLECTION = "alerts"

# =========================================
# Alert Message Templates
# =========================================

ALERT_TEMPLATES = {
    "hypertensive_crisis": {
        "title": "Critical Blood Pressure Detected",
        "body": "Reading of {systolic}/{diastolic} mmHg exceeds safe limits.",
        "guidance_category": "urgent_help",
        "suggested_actions": [
            "Call emergency services",
            "Do not drive",
            "Sit or lie down"
        ]
    },
    "persistent_stage_2": {
        "title": "Consistently High Blood Pressure",
        "body": "Your last 3 readings have all been Stage 2 Hypertension (≥140/90 mmHg).",
        "guidance_category": "consult_professional",
        "suggested_actions": [
            "Schedule a medical appointment",
            "Avoid salt and stimulants",
            "Monitor again in 1 hour"
        ]
    },
    "persistent_stage_1": {
        "title": "Elevated Blood Pressure Pattern",
        "body": "Your last 3 readings have been Stage 1 Hypertension (130-139/80-89 mmHg).",
        "guidance_category": "habit_adjustment",
        "suggested_actions": [
            "Reduce sodium intake",
            "Practice 5 min of deep breathing",
            "Monitor again tomorrow morning"
        ]
    },
    "upward_trend": {
        "title": "Rising Blood Pressure Trend",
        "body": "Your 7-day average systolic has increased by {delta} mmHg compared to last week.",
        "guidance_category": "consult_professional",
        "suggested_actions": [
            "Review recent lifestyle changes",
            "Consider consulting your doctor",
            "Continue monitoring daily"
        ]
    },
    "baseline_drift": {
        "title": "Blood Pressure Shift Detected",
        "body": "Your blood pressure has gradually risen above your personal baseline.",
        "guidance_category": "consult_professional",
        "suggested_actions": [
            "Schedule a check-up",
            "Review medication adherence",
            "Monitor stress levels"
        ]
    },
    "statistical_anomaly": {
        "title": "Unusual Reading Detected",
        "body": "This reading is significantly different from your typical pattern.",
        "guidance_category": "observe",
        "followup_question": "Did you measure after physical activity or stress?",
        "suggested_actions": [
            "Rest for 5 minutes and remeasure",
            "Note any recent activities",
            "Monitor over the next few hours"
        ]
    },
    "critical_tachycardia": {
        "title": "Very High Heart Rate Detected",
        "body": "Your heart rate ({bpm} BPM) is critically elevated.",
        "guidance_category": "urgent_help",
        "suggested_actions": [
            "Stop any physical activity immediately",
            "Sit or lie down",
            "Contact emergency services if symptoms persist"
        ]
    },
    "critical_bradycardia": {
        "title": "Very Low Heart Rate Detected",
        "body": "Your heart rate ({bpm} BPM) is critically low.",
        "guidance_category": "urgent_help",
        "suggested_actions": [
            "Sit down immediately",
            "Contact emergency services",
            "Do not attempt to stand or walk"
        ]
    }
}

# Severity mappings for each alert type
ALERT_SEVERITIES = {
    "hypertensive_crisis": "urgent",
    "persistent_stage_2": "high",
    "persistent_stage_1": "moderate",
    "upward_trend": "moderate",
    "baseline_drift": "moderate",
    "statistical_anomaly": "info",
    "critical_tachycardia": "urgent",
    "critical_bradycardia": "urgent"
}


class AlertGenerator:
    """
    Generates and stores alerts for cardiovascular health monitoring.
    
    Handles deduplication: only one active alert per type per user per 24h,
    except for hypertensive_crisis which always generates.
    """
    
    def __init__(self, db):
        self.db = db
    
    async def can_generate_alert(
        self,
        user_id: str,
        alert_type: str
    ) -> bool:
        """
        Check if an alert of this type can be generated (deduplication check).
        
        Hypertensive crisis alerts are never deduplicated.
        Other alerts are limited to one per type per user per 24 hours.
        
        Args:
            user_id: The user's ID
            alert_type: Type of alert to generate
            
        Returns:
            True if alert can be generated, False if duplicate
        """
        # Hypertensive crisis always generates
        if alert_type == "hypertensive_crisis":
            return True
        
        # Check for existing active alert of this type in last 24 hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        existing = await self.db[ALERTS_COLLECTION].find_one({
            "patient_id": user_id,
            "type": alert_type,
            "status": "active",
            "created_at_iso": {"$gte": cutoff_iso}
        })
        
        return existing is None
    
    async def generate_alert(
        self,
        user_id: str,
        alert_type: str,
        template_vars: Optional[Dict[str, Any]] = None,
        cause: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate and store an alert if deduplication allows.
        
        Args:
            user_id: The user's ID (patient_id)
            alert_type: One of the keys in ALERT_TEMPLATES
            template_vars: Variables to substitute in message templates
            cause: Human-readable explanation of what triggered this alert
            
        Returns:
            The created alert document if generated, None if deduplicated
        """
        # Check deduplication
        if not await self.can_generate_alert(user_id, alert_type):
            logger.debug(
                f"Alert {alert_type} for user {user_id} deduplicated (existing active alert)"
            )
            return None
        
        # Get template
        template = ALERT_TEMPLATES.get(alert_type)
        if not template:
            logger.error(f"Unknown alert type: {alert_type}")
            return None
        
        # Render message with template variables
        vars_dict = template_vars or {}
        title = template["title"]
        body = template["body"].format(**vars_dict) if vars_dict else template["body"]
        
        # Build guidance
        guidance = {
            "category": template["guidance_category"],
            "primary_message": body,
            "followup_question": template.get("followup_question"),
            "suggested_actions": template.get("suggested_actions")
        }
        
        # Create alert document
        now = now_iso()
        alert_doc = {
            "_id": ObjectId(),
            "alert_id": str(uuid.uuid4()),
            "patient_id": user_id,
            "type": alert_type,
            "severity": ALERT_SEVERITIES.get(alert_type, "info"),
            "status": "active",
            "created_at_iso": now,  # ISO 8601 for queries
            "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),  # ms for compatibility
            "title": title,
            "body": body,
            "guidance": guidance,
            "cause": cause
        }
        
        # Store alert
        try:
            await self.db[ALERTS_COLLECTION].insert_one(alert_doc)
            logger.info(
                f"Generated {alert_type} alert for user {user_id}: {alert_doc['alert_id']}"
            )
            
            # Send push notifications to patient and caregivers
            await self._send_alert_push_notifications(
                user_id=user_id,
                alert_type=alert_type,
                title=title,
                body=body,
                severity=alert_doc["severity"]
            )
            
            return alert_doc
        except Exception as e:
            logger.error(f"Failed to store alert: {e}")
            return None
    
    async def _send_alert_push_notifications(
        self,
        user_id: str,
        alert_type: str,
        title: str,
        body: str,
        severity: str
    ):
        """
        Send push notifications for an alert to patient and their caregivers.
        
        This is called after successfully storing an alert.
        """
        if not is_fcm_available():
            logger.debug("FCM not available, skipping push notifications")
            return
        
        try:
            # Import here to avoid circular imports
            from src.domains.pairing.services import PairingService
            
            # Get patient info
            patient = await self.db.users.find_one({"_id": ObjectId(user_id)})
            if not patient:
                logger.warning(f"Patient {user_id} not found for push notification")
                return
            
            patient_name = patient.get("name", "Paciente")
            patient_fcm_token = patient.get("fcmToken")
            
            # Send to patient
            if patient_fcm_token:
                await send_health_alert_push(
                    fcm_tokens=[patient_fcm_token],
                    alert_type=alert_type,
                    title=title,
                    body=body,
                    severity=severity,
                    is_caregiver_notification=False
                )
                logger.debug(f"Sent push notification to patient {user_id}")
            
            # Get caregivers for this patient
            pairing_service = PairingService(self.db)
            caregiver_ids = await pairing_service.get_patient_caregivers(user_id)
            
            if not caregiver_ids:
                logger.debug(f"No caregivers found for patient {user_id}")
                return
            
            # Get FCM tokens for all caregivers
            caregiver_tokens = []
            for caregiver_id in caregiver_ids:
                try:
                    caregiver = await self.db.users.find_one({"_id": ObjectId(caregiver_id)})
                    if caregiver and caregiver.get("fcmToken"):
                        caregiver_tokens.append(caregiver["fcmToken"])
                except Exception as e:
                    logger.error(f"Error getting caregiver {caregiver_id}: {e}")
            
            # Send to all caregivers
            if caregiver_tokens:
                # Modify title/body for caregiver context
                caregiver_title = f"⚠️ {patient_name}: {title}"
                caregiver_body = f"Tu paciente {patient_name} tiene una alerta: {body}"
                
                await send_health_alert_push(
                    fcm_tokens=caregiver_tokens,
                    alert_type=alert_type,
                    title=caregiver_title,
                    body=caregiver_body,
                    patient_id=user_id,
                    patient_name=patient_name,
                    severity=severity,
                    is_caregiver_notification=True
                )
                logger.info(f"Sent push notifications to {len(caregiver_tokens)} caregivers for patient {user_id}")
                
        except Exception as e:
            logger.error(f"Error sending alert push notifications: {e}")
    
    async def generate_bp_crisis_alert(
        self,
        user_id: str,
        systolic: int,
        diastolic: int
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a hypertensive crisis alert.
        
        Args:
            user_id: The user's ID
            systolic: Systolic BP reading
            diastolic: Diastolic BP reading
            
        Returns:
            Created alert document or None
        """
        return await self.generate_alert(
            user_id=user_id,
            alert_type="hypertensive_crisis",
            template_vars={"systolic": systolic, "diastolic": diastolic},
            cause=f"Blood pressure reading {systolic}/{diastolic} mmHg exceeds crisis threshold (>180/>120)"
        )
    
    async def generate_persistent_stage_alert(
        self,
        user_id: str,
        stage: str,
        readings: List[Dict[str, int]]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a persistent hypertension stage alert.
        
        Args:
            user_id: The user's ID
            stage: "hypertension_stage_1" or "hypertension_stage_2"
            readings: List of the last 3 readings with systolic/diastolic
            
        Returns:
            Created alert document or None
        """
        if stage == "hypertension_stage_2":
            alert_type = "persistent_stage_2"
        elif stage == "hypertension_stage_1":
            alert_type = "persistent_stage_1"
        else:
            return None
        
        # Format readings for cause
        readings_str = ", ".join(
            f"{r['systolic']}/{r['diastolic']}" for r in readings
        )
        
        return await self.generate_alert(
            user_id=user_id,
            alert_type=alert_type,
            cause=f"Last 3 readings all {stage}: {readings_str}"
        )
    
    async def generate_trend_alert(
        self,
        user_id: str,
        delta: int,
        current_avg: int,
        previous_avg: int
    ) -> Optional[Dict[str, Any]]:
        """
        Generate an upward trend alert.
        
        Args:
            user_id: The user's ID
            delta: Change in mmHg week-over-week
            current_avg: Current 7-day average systolic
            previous_avg: Previous 7-day average systolic
            
        Returns:
            Created alert document or None
        """
        return await self.generate_alert(
            user_id=user_id,
            alert_type="upward_trend",
            template_vars={"delta": delta},
            cause=f"7-day systolic average increased from {previous_avg} to {current_avg} mmHg (+{delta})"
        )
    
    async def generate_drift_alert(
        self,
        user_id: str,
        cusum_value: float,
        baseline: float
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a baseline drift alert (CUSUM triggered).
        
        Args:
            user_id: The user's ID
            cusum_value: Current CUSUM value
            baseline: Personal baseline systolic
            
        Returns:
            Created alert document or None
        """
        return await self.generate_alert(
            user_id=user_id,
            alert_type="baseline_drift",
            cause=f"CUSUM drift detection triggered (cusum={cusum_value:.1f}, baseline={baseline:.1f} mmHg)"
        )
    
    async def generate_anomaly_alert(
        self,
        user_id: str,
        systolic: int,
        diastolic: int,
        z_systolic: float,
        z_diastolic: float
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a statistical anomaly alert.
        
        Args:
            user_id: The user's ID
            systolic: Current systolic BP
            diastolic: Current diastolic BP
            z_systolic: Z-score for systolic
            z_diastolic: Z-score for diastolic
            
        Returns:
            Created alert document or None
        """
        return await self.generate_alert(
            user_id=user_id,
            alert_type="statistical_anomaly",
            cause=f"Reading {systolic}/{diastolic} is {max(abs(z_systolic), abs(z_diastolic)):.1f} standard deviations from personal baseline"
        )
    
    async def generate_hr_crisis_alert(
        self,
        user_id: str,
        bpm: int,
        crisis_type: str  # "critical_tachycardia" or "critical_bradycardia"
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a critical heart rate alert.
        
        Args:
            user_id: The user's ID
            bpm: Heart rate reading
            crisis_type: "critical_tachycardia" or "critical_bradycardia"
            
        Returns:
            Created alert document or None
        """
        return await self.generate_alert(
            user_id=user_id,
            alert_type=crisis_type,
            template_vars={"bpm": bpm},
            cause=f"Heart rate {bpm} BPM is critically {'high' if 'tachy' in crisis_type else 'low'}"
        )
