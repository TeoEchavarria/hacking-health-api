"""
Tests for F2 — patient health report PDF.

Covers the PDF builder (valid PDF bytes, accents, empty data) and the data
aggregator (assembles BP/adherence/events from mocked domain services).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.domains.reports.service import build_patient_report_pdf, PatientReportService


SAMPLE = {
    "patient_name": "María Ñoño",  # accents + ñ must not crash the latin-1 encoder
    "generated_at": "2026-06-11 10:00 UTC",
    "bp": {"count": 2, "avg_systolic": 130, "avg_diastolic": 85, "readings": [
        {"date": "2026-06-10", "systolic": 140, "diastolic": 90, "pulse": 72, "stage": "stage_1"},
        {"date": "2026-06-09", "systolic": 120, "diastolic": 80, "pulse": 68, "stage": "normal"},
    ]},
    "adherence": {"overall": 87.5, "medications": [
        {"name": "Losartán", "pct": 90.0, "days_taken": 27, "total_days": 30},
    ]},
    "events": [{"severity": "critical", "message": "Crisis hipertensiva", "date": "2026-06-10 08:00"}],
}


def test_build_pdf_returns_pdf_bytes():
    pdf = build_patient_report_pdf(SAMPLE)
    assert isinstance(pdf, (bytes, bytearray))
    assert bytes(pdf[:5]) == b"%PDF-"
    assert len(pdf) > 800


def test_build_pdf_handles_empty_data():
    empty = {
        "patient_name": "X", "generated_at": "now",
        "bp": {"count": 0, "avg_systolic": None, "avg_diastolic": None, "readings": []},
        "adherence": None, "events": [],
    }
    pdf = build_patient_report_pdf(empty)
    assert bytes(pdf[:5]) == b"%PDF-"


class _FakeEventsCursor:
    """Mimics a motor cursor: chainable sort/limit + async iteration."""
    def __init__(self, events):
        self._events = events

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for e in self._events:
            yield e


@pytest.mark.asyncio
async def test_gather_report_data(monkeypatch):
    db = MagicMock()
    collection = MagicMock()
    collection.find.return_value = _FakeEventsCursor(
        [{"severity": "warning", "message": "BP alta", "recordedAt": None}]
    )
    db.__getitem__.return_value = collection

    fake_hs = MagicMock()
    fake_hs.get_patient_blood_pressure_readings = AsyncMock(return_value={
        "patient_name": "Ana", "readings": [{"systolic": 120, "diastolic": 80}],
    })
    fake_ms = MagicMock()
    fake_ms.get_monthly_report = AsyncMock(return_value={
        "overallAdherence": 80.0,
        "medications": [{"medicationName": "X", "adherencePercentage": 80.0, "daysTaken": 24, "totalDays": 30}],
    })
    monkeypatch.setattr("src.domains.reports.service.HealthService", lambda _db: fake_hs)
    monkeypatch.setattr("src.domains.reports.service.MedicationService", lambda _db: fake_ms)

    data = await PatientReportService(db).gather_report_data("p1")
    assert data["patient_name"] == "Ana"
    assert data["bp"]["count"] == 1
    assert data["bp"]["avg_systolic"] == 120
    assert data["adherence"]["overall"] == 80.0
    assert len(data["events"]) == 1

    # End-to-end: the gathered data renders to a valid PDF.
    pdf = build_patient_report_pdf(data)
    assert bytes(pdf[:5]) == b"%PDF-"
