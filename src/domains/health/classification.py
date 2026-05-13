"""
Pure classification functions for cardiovascular health metrics.

These functions are stateless and have no side effects, making them
easily unit-testable and portable to other platforms (e.g., Kotlin for mobile).

Clinical thresholds follow AHA/ACC 2025 guidelines.

Classification functions now use Strategy Pattern (see strategies/ module)
following the Open-Closed Principle for easy extensibility.
"""
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta

# Import classification strategies (Strategy Pattern)
from .strategies.bp_classification import classify_blood_pressure
from .strategies.hr_classification import classify_heart_rate


# Re-export for backward compatibility
__all__ = [
    'classify_blood_pressure',
    'classify_heart_rate',
    'validate_bp_reading',
    'validate_heart_rate_reading',
    'detect_crisis'
]


# =========================================
# Physiological Validation
# =========================================

def validate_bp_reading(
    systolic: int,
    diastolic: int,
    pulse: Optional[int] = None,
    timestamp: Optional[str] = None,
    clock_drift_minutes: int = 2
) -> Tuple[bool, Optional[str]]:
    """
    Validate a blood pressure reading for physiological plausibility.
    
    Validation rules (in order):
        1. Systolic must be between 60 and 300 mmHg
        2. Diastolic must be between 30 and 200 mmHg
        3. Systolic must be strictly greater than diastolic
        4. Pulse (if present) must be between 20 and 300 BPM
        5. Timestamp must not be in the future (allow ±clock_drift_minutes)
    
    Args:
        systolic: Systolic blood pressure in mmHg
        diastolic: Diastolic blood pressure in mmHg
        pulse: Optional pulse reading in BPM
        timestamp: Optional ISO 8601 timestamp string
        clock_drift_minutes: Allowed clock drift for future timestamp check
        
    Returns:
        Tuple of (is_valid, error_message or None)
    """
    # Rule 1: Systolic range
    if not (60 <= systolic <= 300):
        return False, "Systolic BP out of physiologically plausible range (60-300 mmHg)"
    
    # Rule 2: Diastolic range
    if not (30 <= diastolic <= 200):
        return False, "Diastolic BP out of physiologically plausible range (30-200 mmHg)"
    
    # Rule 3: Systolic > Diastolic
    if systolic <= diastolic:
        return False, "Systolic must be greater than diastolic"
    
    # Rule 4: Pulse range (if provided)
    if pulse is not None and not (20 <= pulse <= 300):
        return False, "Pulse out of physiologically plausible range (20-300 BPM)"
    
    # Rule 5: Timestamp not in future (if provided)
    if timestamp is not None:
        try:
            ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            max_allowed = now + timedelta(minutes=clock_drift_minutes)
            if ts > max_allowed:
                return False, "Timestamp cannot be in the future"
        except (ValueError, AttributeError):
            return False, "Invalid timestamp format (expected ISO 8601)"
    
    return True, None


def validate_heart_rate_reading(
    bpm: int,
    timestamp: Optional[str] = None,
    clock_drift_minutes: int = 2
) -> Tuple[bool, Optional[str]]:
    """
    Validate a heart rate reading for physiological plausibility.
    
    Args:
        bpm: Heart rate in beats per minute
        timestamp: Optional ISO 8601 timestamp string
        clock_drift_minutes: Allowed clock drift for future timestamp check
        
    Returns:
        Tuple of (is_valid, error_message or None)
    """
    # BPM range
    if not (20 <= bpm <= 300):
        return False, "BPM out of physiologically plausible range (20-300)"
    
    # Timestamp not in future (if provided)
    if timestamp is not None:
        try:
            ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            max_allowed = now + timedelta(minutes=clock_drift_minutes)
            if ts > max_allowed:
                return False, "Timestamp cannot be in the future"
        except (ValueError, AttributeError):
            return False, "Invalid timestamp format (expected ISO 8601)"
    
    return True, None


# =========================================
# Crisis Detection (Edge/Mobile)
# =========================================

def detect_crisis(
    systolic: Optional[int] = None,
    diastolic: Optional[int] = None,
    pulse: Optional[int] = None
) -> Optional[Dict[str, str]]:
    """
    Detect immediate crisis conditions for edge/mobile processing.
    
    This function is designed for immediate alerting on the device,
    running in parallel with API submission.
    
    Crisis conditions:
        - Hypertensive Crisis: SBP > 180 OR DBP > 120
        - Critical Tachycardia: Pulse > 150
        - Critical Bradycardia: Pulse < 40
    
    Args:
        systolic: Systolic blood pressure in mmHg (optional)
        diastolic: Diastolic blood pressure in mmHg (optional)
        pulse: Heart rate in BPM (optional)
        
    Returns:
        Dict with crisis info if detected, None otherwise
        Keys: type, severity, title, body, guidance_category
    """
    # Hypertensive Crisis
    if systolic is not None and diastolic is not None:
        if systolic > 180 or diastolic > 120:
            return {
                "type": "hypertensive_crisis",
                "severity": "urgent",
                "title": "Critical Blood Pressure Reading",
                "body": f"Your blood pressure ({systolic}/{diastolic} mmHg) is at a dangerous level. "
                        "Seek emergency medical attention immediately.",
                "guidance_category": "urgent_help"
            }
    
    # Critical Tachycardia
    if pulse is not None and pulse > 150:
        return {
            "type": "critical_tachycardia",
            "severity": "urgent",
            "title": "Very High Heart Rate Detected",
            "body": f"Your heart rate ({pulse} BPM) is critically elevated. Rest immediately "
                    "and contact emergency services if you feel chest pain or dizziness.",
            "guidance_category": "urgent_help"
        }
    
    # Critical Bradycardia
    if pulse is not None and pulse < 40:
        return {
            "type": "critical_bradycardia",
            "severity": "urgent",
            "title": "Very Low Heart Rate Detected",
            "body": f"Your heart rate ({pulse} BPM) is critically low. "
                    "Seek medical attention immediately.",
            "guidance_category": "urgent_help"
        }
    
    return None
