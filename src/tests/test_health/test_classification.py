"""
Unit tests for cardiovascular classification functions.

Uses the Gold Standard test vectors from classification_test_vectors.json
to ensure consistent behavior between Python and Kotlin implementations.
"""
import pytest
import json
from pathlib import Path

from src.domains.health.classification import (
    classify_blood_pressure,
    classify_heart_rate,
    detect_crisis,
    validate_bp_reading
)


# Load test vectors
TEST_VECTORS_PATH = Path(__file__).parent / "classification_test_vectors.json"
with open(TEST_VECTORS_PATH, "r") as f:
    TEST_VECTORS = json.load(f)


class TestBloodPressureClassification:
    """Test blood pressure classification against AHA/ACC 2025 guidelines."""
    
    @pytest.mark.parametrize("test_case", TEST_VECTORS["blood_pressure_tests"])
    def test_blood_pressure_classification(self, test_case):
        """Test BP classification for all defined test vectors."""
        input_data = test_case["input"]
        expected = test_case["expected"]
        
        result = classify_blood_pressure(
            systolic=input_data["systolic"],
            diastolic=input_data["diastolic"]
        )
        
        assert result["stage"] == expected["stage"], (
            f"Test {test_case['id']}: Expected stage '{expected['stage']}', "
            f"got '{result['stage']}' for {input_data}"
        )
        assert result["severity"] == expected["severity"], (
            f"Test {test_case['id']}: Expected severity '{expected['severity']}', "
            f"got '{result['severity']}'"
        )
        assert result["label"] == expected["label"], (
            f"Test {test_case['id']}: Expected label '{expected['label']}', "
            f"got '{result['label']}'"
        )
        assert result["guideline"] == "AHA/ACC 2025"
    
    def test_normal_bp(self):
        """Test normal blood pressure classification."""
        result = classify_blood_pressure(115, 75)
        assert result["stage"] == "normal"
        assert result["severity"] == "info"
    
    def test_elevated_bp(self):
        """Test elevated blood pressure classification."""
        result = classify_blood_pressure(125, 75)
        assert result["stage"] == "elevated"
        assert result["severity"] == "info"
    
    def test_stage1_hypertension_by_systolic(self):
        """Test Stage 1 hypertension triggered by systolic."""
        result = classify_blood_pressure(135, 75)
        assert result["stage"] == "hypertension_stage_1"
        assert result["severity"] == "moderate"
    
    def test_stage1_hypertension_by_diastolic(self):
        """Test Stage 1 hypertension triggered by diastolic."""
        result = classify_blood_pressure(115, 85)
        assert result["stage"] == "hypertension_stage_1"
        assert result["severity"] == "moderate"
    
    def test_stage2_hypertension_by_systolic(self):
        """Test Stage 2 hypertension triggered by systolic."""
        result = classify_blood_pressure(145, 75)
        assert result["stage"] == "hypertension_stage_2"
        assert result["severity"] == "high"
    
    def test_stage2_hypertension_by_diastolic(self):
        """Test Stage 2 hypertension triggered by diastolic."""
        result = classify_blood_pressure(125, 95)
        assert result["stage"] == "hypertension_stage_2"
        assert result["severity"] == "high"
    
    def test_hypertensive_crisis_by_systolic(self):
        """Test hypertensive crisis triggered by systolic > 180."""
        result = classify_blood_pressure(185, 100)
        assert result["stage"] == "hypertensive_crisis"
        assert result["severity"] == "urgent"
    
    def test_hypertensive_crisis_by_diastolic(self):
        """Test hypertensive crisis triggered by diastolic > 120."""
        result = classify_blood_pressure(150, 125)
        assert result["stage"] == "hypertensive_crisis"
        assert result["severity"] == "urgent"


class TestHeartRateClassification:
    """Test heart rate classification for adult resting heart rate."""
    
    @pytest.mark.parametrize("test_case", TEST_VECTORS["heart_rate_tests"])
    def test_heart_rate_classification(self, test_case):
        """Test HR classification for all defined test vectors."""
        input_data = test_case["input"]
        expected = test_case["expected"]
        
        result = classify_heart_rate(bpm=input_data["bpm"])
        
        assert result["category"] == expected["category"], (
            f"Test {test_case['id']}: Expected category '{expected['category']}', "
            f"got '{result['category']}' for BPM {input_data['bpm']}"
        )
        assert result["severity"] == expected["severity"]
        assert result["label"] == expected["label"]
    
    def test_critical_bradycardia(self):
        """Test critical bradycardia detection (BPM < 40)."""
        result = classify_heart_rate(35)
        assert result["category"] == "critical_bradycardia"
        assert result["severity"] == "urgent"
    
    def test_bradycardia(self):
        """Test bradycardia detection (BPM 40-59)."""
        result = classify_heart_rate(50)
        assert result["category"] == "bradycardia"
        assert result["severity"] == "moderate"
    
    def test_normal_hr(self):
        """Test normal heart rate (BPM 60-100)."""
        result = classify_heart_rate(72)
        assert result["category"] == "normal"
        assert result["severity"] == "info"
    
    def test_tachycardia(self):
        """Test tachycardia detection (BPM 101-150)."""
        result = classify_heart_rate(120)
        assert result["category"] == "tachycardia"
        assert result["severity"] == "moderate"
    
    def test_critical_tachycardia(self):
        """Test critical tachycardia detection (BPM > 150)."""
        result = classify_heart_rate(160)
        assert result["category"] == "critical_tachycardia"
        assert result["severity"] == "urgent"


class TestCrisisDetection:
    """Test crisis detection for edge/mobile processing."""
    
    @pytest.mark.parametrize("test_case", TEST_VECTORS["crisis_detection_tests"])
    def test_crisis_detection(self, test_case):
        """Test crisis detection for all defined test vectors."""
        input_data = test_case["input"]
        expected = test_case["expected"]
        
        result = detect_crisis(
            systolic=input_data.get("systolic"),
            diastolic=input_data.get("diastolic"),
            pulse=input_data.get("pulse")
        )
        
        if expected is None:
            assert result is None, (
                f"Test {test_case['id']}: Expected no crisis, "
                f"got {result} for {input_data}"
            )
        else:
            assert result is not None, (
                f"Test {test_case['id']}: Expected crisis, got None for {input_data}"
            )
            assert result["type"] == expected["type"], (
                f"Test {test_case['id']}: Expected type '{expected['type']}', "
                f"got '{result['type']}'"
            )
            assert result["severity"] == expected["severity"]
            assert result["guidance_category"] == expected["guidance_category"]
    
    def test_no_crisis_normal_values(self):
        """Test that normal values don't trigger crisis."""
        result = detect_crisis(systolic=120, diastolic=80, pulse=72)
        assert result is None
    
    def test_hypertensive_crisis(self):
        """Test hypertensive crisis detection."""
        result = detect_crisis(systolic=190, diastolic=100, pulse=80)
        assert result is not None
        assert result["type"] == "hypertensive_crisis"
        assert result["severity"] == "urgent"
    
    def test_critical_tachycardia_crisis(self):
        """Test critical tachycardia crisis detection."""
        result = detect_crisis(systolic=120, diastolic=80, pulse=160)
        assert result is not None
        assert result["type"] == "critical_tachycardia"
    
    def test_critical_bradycardia_crisis(self):
        """Test critical bradycardia crisis detection."""
        result = detect_crisis(systolic=120, diastolic=80, pulse=35)
        assert result is not None
        assert result["type"] == "critical_bradycardia"
    
    def test_hypertensive_takes_priority(self):
        """Test that hypertensive crisis takes priority over pulse crisis."""
        result = detect_crisis(systolic=200, diastolic=130, pulse=160)
        assert result["type"] == "hypertensive_crisis"


class TestBPValidation:
    """Test blood pressure reading validation."""
    
    @pytest.mark.parametrize("test_case", TEST_VECTORS["validation_tests"])
    def test_bp_validation(self, test_case):
        """Test BP validation for all defined test vectors."""
        input_data = test_case["input"]
        expected = test_case["expected"]
        
        is_valid, error = validate_bp_reading(
            systolic=input_data["systolic"],
            diastolic=input_data["diastolic"],
            pulse=input_data.get("pulse"),
            timestamp=input_data.get("timestamp")
        )
        
        assert is_valid == expected["is_valid"], (
            f"Test {test_case['id']}: Expected is_valid={expected['is_valid']}, "
            f"got {is_valid}. Error: {error}"
        )
        
        if not expected["is_valid"]:
            assert error == expected["error"], (
                f"Test {test_case['id']}: Expected error '{expected['error']}', "
                f"got '{error}'"
            )
    
    def test_valid_reading(self):
        """Test that a valid reading passes validation."""
        is_valid, error = validate_bp_reading(120, 80, 72, "2025-04-24T10:30:00Z")
        assert is_valid is True
        assert error is None
    
    def test_systolic_too_low(self):
        """Test that systolic < 60 fails."""
        is_valid, error = validate_bp_reading(55, 50, None, None)
        assert is_valid is False
        assert "Systolic" in error
    
    def test_systolic_too_high(self):
        """Test that systolic > 300 fails."""
        is_valid, error = validate_bp_reading(310, 150, None, None)
        assert is_valid is False
        assert "Systolic" in error
    
    def test_diastolic_too_low(self):
        """Test that diastolic < 30 fails."""
        is_valid, error = validate_bp_reading(120, 25, None, None)
        assert is_valid is False
        assert "Diastolic" in error
    
    def test_diastolic_too_high(self):
        """Test that diastolic > 200 fails."""
        is_valid, error = validate_bp_reading(220, 210, None, None)
        assert is_valid is False
        assert "Diastolic" in error
    
    def test_systolic_must_exceed_diastolic(self):
        """Test that systolic must be greater than diastolic."""
        is_valid, error = validate_bp_reading(80, 90, None, None)
        assert is_valid is False
        assert "greater than diastolic" in error
    
    def test_pulse_too_low(self):
        """Test that pulse < 20 fails."""
        is_valid, error = validate_bp_reading(120, 80, 15, None)
        assert is_valid is False
        assert "Pulse" in error
    
    def test_pulse_too_high(self):
        """Test that pulse > 300 fails."""
        is_valid, error = validate_bp_reading(120, 80, 310, None)
        assert is_valid is False
        assert "Pulse" in error
    
    def test_invalid_timestamp_format(self):
        """Test that invalid timestamp format fails."""
        is_valid, error = validate_bp_reading(120, 80, 72, "not-a-timestamp")
        assert is_valid is False
        assert "timestamp" in error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
