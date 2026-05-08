"""
Firebase Cloud Messaging client for sending push notifications.

This module handles:
- Firebase Admin SDK initialization
- Sending push notifications to individual devices
- Sending batch notifications to multiple devices

Environment variables required:
- GOOGLE_APPLICATION_CREDENTIALS: Path to Firebase service account JSON
  OR
- FIREBASE_SERVICE_ACCOUNT_JSON: Base64-encoded service account JSON
"""
import os
import json
import base64
from typing import Optional, Dict, Any, List
from src._config.logger import get_logger

logger = get_logger(__name__)

# Firebase Admin SDK - optional dependency
_firebase_app = None
_messaging = None

def _initialize_firebase():
    """
    Initialize Firebase Admin SDK.
    
    Looks for credentials in:
    1. GOOGLE_APPLICATION_CREDENTIALS environment variable (path to JSON)
    2. FIREBASE_SERVICE_ACCOUNT_JSON environment variable (base64-encoded JSON)
    
    Returns True if initialization successful, False otherwise.
    """
    global _firebase_app, _messaging
    
    if _firebase_app is not None:
        return True
    
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
        
        # Try to get credentials
        creds = None
        
        # Option 1: Path to credentials file
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and os.path.exists(creds_path):
            creds = credentials.Certificate(creds_path)
            logger.info(f"Firebase initialized with credentials from: {creds_path}")
        
        # Option 2: Base64-encoded JSON in environment variable
        if creds is None:
            creds_b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
            if creds_b64:
                try:
                    creds_json = base64.b64decode(creds_b64).decode('utf-8')
                    creds_dict = json.loads(creds_json)
                    creds = credentials.Certificate(creds_dict)
                    logger.info("Firebase initialized with credentials from FIREBASE_SERVICE_ACCOUNT_JSON")
                except Exception as e:
                    logger.error(f"Failed to decode FIREBASE_SERVICE_ACCOUNT_JSON: {e}")
        
        if creds is None:
            logger.warning("No Firebase credentials found. Push notifications disabled.")
            return False
        
        _firebase_app = firebase_admin.initialize_app(creds)
        _messaging = messaging
        
        logger.info("Firebase Admin SDK initialized successfully")
        return True
        
    except ImportError:
        logger.warning("firebase-admin not installed. Push notifications disabled.")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        return False


def is_fcm_available() -> bool:
    """Check if FCM is available and initialized."""
    return _initialize_firebase()


async def send_push_notification(
    fcm_token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
    image_url: Optional[str] = None
) -> bool:
    """
    Send a push notification to a single device.
    
    Args:
        fcm_token: The device's FCM registration token
        title: Notification title
        body: Notification body text
        data: Optional data payload (key-value pairs, all strings)
        image_url: Optional image URL for rich notifications
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    if not _initialize_firebase():
        logger.warning("FCM not available, skipping push notification")
        return False
    
    try:
        # Build notification
        notification = _messaging.Notification(
            title=title,
            body=body,
            image=image_url
        )
        
        # Build Android config for high priority
        android_config = _messaging.AndroidConfig(
            priority='high',
            notification=_messaging.AndroidNotification(
                channel_id='vitals_alerts',
                priority='max',
                default_vibrate_timings=True,
                default_light_settings=True
            )
        )
        
        # Build message
        message = _messaging.Message(
            notification=notification,
            data=data or {},
            android=android_config,
            token=fcm_token
        )
        
        # Send
        response = _messaging.send(message)
        logger.info(f"Push notification sent successfully: {response}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send push notification: {e}")
        return False


async def send_push_to_multiple(
    fcm_tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Send push notification to multiple devices.
    
    Args:
        fcm_tokens: List of FCM registration tokens
        title: Notification title
        body: Notification body text
        data: Optional data payload
        
    Returns:
        Dict with 'success_count', 'failure_count', and 'responses'
    """
    if not _initialize_firebase():
        logger.warning("FCM not available, skipping push notifications")
        return {"success_count": 0, "failure_count": len(fcm_tokens), "responses": []}
    
    if not fcm_tokens:
        return {"success_count": 0, "failure_count": 0, "responses": []}
    
    try:
        # Build notification
        notification = _messaging.Notification(
            title=title,
            body=body
        )
        
        # Build Android config
        android_config = _messaging.AndroidConfig(
            priority='high',
            notification=_messaging.AndroidNotification(
                channel_id='vitals_alerts',
                priority='max'
            )
        )
        
        # Build messages for each token
        messages = [
            _messaging.Message(
                notification=notification,
                data=data or {},
                android=android_config,
                token=token
            )
            for token in fcm_tokens
        ]
        
        # Send all (batch send)
        response = _messaging.send_each(messages)
        
        result = {
            "success_count": response.success_count,
            "failure_count": response.failure_count,
            "responses": []
        }
        
        for i, send_response in enumerate(response.responses):
            if send_response.success:
                result["responses"].append({"token": fcm_tokens[i], "success": True})
            else:
                result["responses"].append({
                    "token": fcm_tokens[i], 
                    "success": False, 
                    "error": str(send_response.exception)
                })
        
        logger.info(
            f"Batch push: {response.success_count} success, "
            f"{response.failure_count} failures"
        )
        return result
        
    except Exception as e:
        logger.error(f"Failed to send batch push notifications: {e}")
        return {
            "success_count": 0, 
            "failure_count": len(fcm_tokens), 
            "responses": []
        }


async def send_health_alert_push(
    fcm_tokens: List[str],
    alert_type: str,
    title: str,
    body: str,
    patient_id: Optional[str] = None,
    patient_name: Optional[str] = None,
    severity: str = "info",
    is_caregiver_notification: bool = False
) -> Dict[str, Any]:
    """
    Send a health alert push notification.
    
    This is a specialized function for health-related alerts that includes
    additional metadata in the data payload.
    
    Args:
        fcm_tokens: List of FCM tokens to notify
        alert_type: Type of alert (e.g., "hypertensive_crisis")
        title: Notification title
        body: Notification body
        patient_id: ID of the patient (for caregiver notifications)
        patient_name: Name of the patient (for caregiver notifications)
        severity: Alert severity ("urgent", "high", "moderate", "info")
        is_caregiver_notification: Whether this is for caregivers
        
    Returns:
        Result dict with success/failure counts
    """
    data = {
        "type": "caregiver_alert" if is_caregiver_notification else "health_alert",
        "alert_type": alert_type,
        "severity": severity
    }
    
    if patient_id:
        data["patient_id"] = patient_id
    if patient_name:
        data["patient_name"] = patient_name
    
    return await send_push_to_multiple(
        fcm_tokens=fcm_tokens,
        title=title,
        body=body,
        data=data
    )
