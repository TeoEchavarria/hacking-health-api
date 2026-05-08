"""
Tests for utility formatters.
"""
import pytest
from src.utils.formatters import format_sleep_duration


class TestFormatSleepDuration:
    """Tests for format_sleep_duration function."""
    
    def test_none_returns_no_disponible(self):
        """None input returns 'No disponible'."""
        assert format_sleep_duration(None) == "No disponible"
    
    def test_negative_returns_no_disponible(self):
        """Negative input returns 'No disponible'."""
        assert format_sleep_duration(-10) == "No disponible"
    
    def test_zero_returns_zero_minutos(self):
        """Zero minutes returns '0 minutos'."""
        assert format_sleep_duration(0) == "0 minutos"
    
    def test_only_minutes(self):
        """Minutes less than 60 show only minutes."""
        assert format_sleep_duration(45) == "45 minutos"
        assert format_sleep_duration(1) == "1 minuto"
        assert format_sleep_duration(59) == "59 minutos"
    
    def test_exact_hour(self):
        """Exact hours show only hours."""
        assert format_sleep_duration(60) == "1 hora"
        assert format_sleep_duration(120) == "2 horas"
        assert format_sleep_duration(480) == "8 horas"
    
    def test_hours_and_minutes(self):
        """Mix of hours and minutes shows both."""
        assert format_sleep_duration(400) == "6 horas 40 minutos"
        assert format_sleep_duration(90) == "1 hora 30 minutos"
        assert format_sleep_duration(61) == "1 hora 1 minuto"
        assert format_sleep_duration(121) == "2 horas 1 minuto"
    
    @pytest.mark.parametrize("minutes,expected", [
        (0, "0 minutos"),
        (1, "1 minuto"),
        (30, "30 minutos"),
        (59, "59 minutos"),
        (60, "1 hora"),
        (61, "1 hora 1 minuto"),
        (90, "1 hora 30 minutos"),
        (119, "1 hora 59 minutos"),
        (120, "2 horas"),
        (121, "2 horas 1 minuto"),
        (150, "2 horas 30 minutos"),
        (400, "6 horas 40 minutos"),
        (480, "8 horas"),
        (540, "9 horas"),
        (600, "10 horas"),
    ])
    def test_parametrized_cases(self, minutes, expected):
        """Test various minute values with expected outputs."""
        assert format_sleep_duration(minutes) == expected
