"""
Unit tests for the medication-take voice flow (sub-flow B:
"ya me tomé las de la mañana").

Covers the deterministic pieces that do not require the OpenAI API or a real
database:
  - the keyword intent fallback (VoiceParsingService._try_keyword_take_intent)
  - the franja hour mapping (MedicationService._hour_in_franja)
  - the slot resolution (MedicationService.resolve_pending_takes_for_franja)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.domains.health.voice_parsing import VoiceParsingService
from src.domains.medications.services import MedicationService


@pytest.fixture
def voice():
    return VoiceParsingService()


# ---------------------------------------------------------------------------
# Keyword intent fallback
# ---------------------------------------------------------------------------

class TestKeywordTakeIntent:
    def test_morning(self, voice):
        r = voice._try_keyword_take_intent("Hola, ya me tomé las pastillas de la mañana")
        assert r == {"intent": "confirm_take", "franja": "morning", "confidence": "high"}

    def test_midday_tarde(self, voice):
        r = voice._try_keyword_take_intent("ya me tomé las de la tarde")
        assert r["intent"] == "confirm_take"
        assert r["franja"] == "midday"

    def test_night(self, voice):
        r = voice._try_keyword_take_intent("listo, me tomé las de la noche")
        assert r["intent"] == "confirm_take"
        assert r["franja"] == "night"

    def test_all(self, voice):
        r = voice._try_keyword_take_intent("ya me las tomé todas")
        assert r["intent"] == "confirm_take"
        assert r["franja"] == "all"

    def test_specific_franja_wins_over_all(self, voice):
        r = voice._try_keyword_take_intent("ya me tomé todas las de la mañana")
        assert r["franja"] == "morning"

    def test_question_is_unknown(self, voice):
        r = voice._try_keyword_take_intent("¿a qué hora me toca la siguiente?")
        assert r["intent"] == "unknown"
        assert r["confidence"] == "low"

    def test_take_without_franja_is_low_confidence(self, voice):
        r = voice._try_keyword_take_intent("ya me tomé la pastilla")
        assert r["intent"] == "confirm_take"
        assert r["franja"] is None
        assert r["confidence"] == "low"


# ---------------------------------------------------------------------------
# Franja hour mapping
# ---------------------------------------------------------------------------

class TestHourInFranja:
    def test_morning(self):
        assert MedicationService._hour_in_franja(8, "morning")
        assert not MedicationService._hour_in_franja(13, "morning")

    def test_midday(self):
        assert MedicationService._hour_in_franja(14, "midday")
        assert not MedicationService._hour_in_franja(20, "midday")

    def test_night_wraps_midnight(self):
        assert MedicationService._hour_in_franja(21, "night")
        assert MedicationService._hour_in_franja(2, "night")
        assert not MedicationService._hour_in_franja(10, "night")

    def test_all(self):
        assert MedicationService._hour_in_franja(0, "all")
        assert MedicationService._hour_in_franja(23, "all")

    def test_unknown_franja(self):
        assert not MedicationService._hour_in_franja(10, "bogus")


# ---------------------------------------------------------------------------
# resolve_pending_takes_for_franja
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestResolveFranja:
    @staticmethod
    def _svc_with_status(status):
        svc = MedicationService(MagicMock())
        svc.get_medications_with_today_status = AsyncMock(return_value=status)
        return svc

    async def test_returns_morning_slot_not_taken(self):
        status = [{
            "medication": {"id": "m1", "name": "Losartán", "dosage": "50mg", "times": ["08:00", "20:00"]},
            "takes": [],
            "isTakenToday": False,
        }]
        svc = self._svc_with_status(status)
        pending = await svc.resolve_pending_takes_for_franja("u1", "morning")
        assert pending == [
            {"medication_id": "m1", "name": "Losartán", "dosage": "50mg", "scheduled_time": "08:00"}
        ]

    async def test_excludes_already_taken_slot(self):
        status = [{
            "medication": {"id": "m1", "name": "Losartán", "dosage": "50mg", "times": ["08:00"]},
            "takes": [{"scheduledTime": "08:00"}],
            "isTakenToday": True,
        }]
        svc = self._svc_with_status(status)
        pending = await svc.resolve_pending_takes_for_franja("u1", "morning")
        assert pending == []

    async def test_all_returns_every_pending_slot(self):
        status = [{
            "medication": {"id": "m1", "name": "Metformina", "dosage": "", "times": ["08:00", "21:00"]},
            "takes": [{"scheduledTime": "08:00"}],
            "isTakenToday": False,
        }]
        svc = self._svc_with_status(status)
        pending = await svc.resolve_pending_takes_for_franja("u1", "all")
        assert pending == [
            {"medication_id": "m1", "name": "Metformina", "dosage": "", "scheduled_time": "21:00"}
        ]

    async def test_invalid_franja_returns_empty(self):
        svc = self._svc_with_status([])
        assert await svc.resolve_pending_takes_for_franja("u1", "bogus") == []
