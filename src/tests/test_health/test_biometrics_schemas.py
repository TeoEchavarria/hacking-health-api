"""
Tests for health schemas - specifically biometrics models.
"""
import pytest
from pydantic import ValidationError
from src.domains.health.schemas import (
    HealthMetricsInput,
    BiometricsLatest,
    BiometricsHistoryRecord,
    BiometricsHistoryResponse,
)


class TestHealthMetricsInput:
    """Tests for HealthMetricsInput schema."""
    
    def test_valid_input_with_all_fields(self):
        """Test valid input with all optional fields."""
        data = HealthMetricsInput(
            user_id="user123",
            date="2026-05-08",
            steps=10000,
            sleep_minutes=420,
            avg_heart_rate=72,
            min_heart_rate=55,
            max_heart_rate=120,
            sync_timestamp="2026-05-08T10:30:00Z",
            source="watch"
        )
        assert data.user_id == "user123"
        assert data.steps == 10000
        assert data.source == "watch"
    
    def test_valid_input_minimal(self):
        """Test valid input with only required fields."""
        data = HealthMetricsInput(
            user_id="user123",
            date="2026-05-08",
            sync_timestamp="2026-05-08T10:30:00Z"
        )
        assert data.user_id == "user123"
        assert data.steps is None
        assert data.source is None
    
    def test_source_accepts_any_string(self):
        """Test that source accepts any string (not just enum values)."""
        data = HealthMetricsInput(
            user_id="user123",
            date="2026-05-08",
            sync_timestamp="2026-05-08T10:30:00Z",
            source="custom_device_xyz"
        )
        assert data.source == "custom_device_xyz"
    
    def test_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            HealthMetricsInput(date="2026-05-08", sync_timestamp="2026-05-08T10:30:00Z")
        
        with pytest.raises(ValidationError):
            HealthMetricsInput(user_id="user123", sync_timestamp="2026-05-08T10:30:00Z")
        
        with pytest.raises(ValidationError):
            HealthMetricsInput(user_id="user123", date="2026-05-08")


class TestBiometricsLatest:
    """Tests for BiometricsLatest schema."""
    
    def test_all_fields(self):
        """Test with all fields populated."""
        data = BiometricsLatest(
            heartRate=72,
            heartRateMin=55,
            heartRateMax=120,
            steps=10000,
            sleepMinutes=420,
            sleepFormatted="7 horas"
        )
        assert data.heartRate == 72
        assert data.sleepFormatted == "7 horas"
    
    def test_all_fields_none(self):
        """Test with all fields as None (new user scenario)."""
        data = BiometricsLatest()
        assert data.heartRate is None
        assert data.steps is None
        assert data.sleepMinutes is None
        assert data.sleepFormatted is None


class TestBiometricsHistoryRecord:
    """Tests for BiometricsHistoryRecord schema."""
    
    def test_valid_record(self):
        """Test valid history record."""
        data = BiometricsHistoryRecord(
            id="507f1f77bcf86cd799439011",
            type="heart_rate",
            value=72,
            date="2026-05-08",
            timestamp="2026-05-08T10:30:00Z",
            source="watch"
        )
        assert data.id == "507f1f77bcf86cd799439011"
        assert data.type == "heart_rate"
        assert data.source == "watch"
    
    def test_value_can_be_none(self):
        """Test that value can be None for certain record types."""
        data = BiometricsHistoryRecord(
            id="507f1f77bcf86cd799439011",
            type="heart_rate_sample",
            value=None,
            date="2026-05-08",
            timestamp="2026-05-08T10:30:00Z",
            source="watch"
        )
        assert data.value is None


class TestBiometricsHistoryResponse:
    """Tests for BiometricsHistoryResponse schema."""
    
    def test_empty_response_for_new_user(self):
        """Test empty response structure for new users."""
        data = BiometricsHistoryResponse(
            isEmpty=True,
            latest=None,
            history=[],
            count=0
        )
        assert data.isEmpty is True
        assert data.latest is None
        assert data.history == []
        assert data.count == 0
    
    def test_response_with_data(self):
        """Test response with biometric data."""
        latest = BiometricsLatest(
            heartRate=72,
            steps=10000,
            sleepMinutes=420,
            sleepFormatted="7 horas"
        )
        record = BiometricsHistoryRecord(
            id="507f1f77bcf86cd799439011",
            type="heart_rate",
            value=72,
            date="2026-05-08",
            timestamp="2026-05-08T10:30:00Z",
            source="watch"
        )
        
        data = BiometricsHistoryResponse(
            isEmpty=False,
            latest=latest,
            history=[record],
            count=1
        )
        
        assert data.isEmpty is False
        assert data.latest.heartRate == 72
        assert len(data.history) == 1
        assert data.history[0].type == "heart_rate"
        assert data.count == 1
