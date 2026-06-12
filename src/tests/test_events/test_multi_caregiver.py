"""
Tests for F4 — multi-caregiver biometric events.

A patient may be linked to several active caregivers; biometric events, alerts
and the medication escalation must reach ALL of them (push + visibility), and
read-state must be tracked per caregiver. These tests cover the deterministic
model/helper logic plus the fan-out in register_biometric_event (mocked DB).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId

from src.domains.events.models import BiometricEventDB
from src.domains.events.services import BiometricEventService, _is_caregiver_view
from src.domains.pairing.services import PairingService


class TestEventModelMultiCaregiver:
    def test_create_document_stores_all_caregivers(self):
        doc = BiometricEventDB.create_document(
            patient_id="p1", event_type="manual_alert", payload={},
            message="m", severity="critical", caregiver_ids=["c1", "c2"],
        )
        assert doc["caregiverIds"] == ["c1", "c2"]
        assert doc["caregiverId"] == "c1"          # legacy first caregiver
        assert doc["readByCaregivers"] == []

    def test_create_document_from_legacy_single(self):
        doc = BiometricEventDB.create_document(
            patient_id="p1", event_type="manual_alert", payload={},
            message="m", caregiver_id="c1",
        )
        assert doc["caregiverIds"] == ["c1"]
        assert doc["caregiverId"] == "c1"

    def test_to_response_read_is_per_caregiver(self):
        doc = {
            "_id": ObjectId(), "patientId": "p1", "caregiverId": "c1",
            "caregiverIds": ["c1", "c2"], "type": "manual_alert", "severity": "critical",
            "payload": {}, "message": "m", "readByPatient": False,
            "readByCaregivers": ["c2"], "recordedAt": None, "createdAt": None,
        }
        assert BiometricEventDB.to_response(doc, requesting_user_id="c2")["read_by_caregiver"] is True
        assert BiometricEventDB.to_response(doc, requesting_user_id="c1")["read_by_caregiver"] is False
        # legacy field preserved + new list exposed
        r1 = BiometricEventDB.to_response(doc, requesting_user_id="c1")
        assert r1["caregiver_id"] == "c1"
        assert r1["caregiver_ids"] == ["c1", "c2"]

    def test_to_response_legacy_doc_without_ids(self):
        doc = {
            "_id": ObjectId(), "patientId": "p1", "caregiverId": "c1",
            "type": "manual_alert", "severity": "info", "payload": {}, "message": "m",
            "readByPatient": False, "readByCaregiver": True,
            "recordedAt": None, "createdAt": None,
        }
        r = BiometricEventDB.to_response(doc, requesting_user_id="c1")
        assert r["caregiver_ids"] == ["c1"]
        assert r["read_by_caregiver"] is True  # honors legacy single-bool


class TestIsCaregiverView:
    def test_membership(self):
        assert _is_caregiver_view({"caregiverIds": ["c1", "c2"]}, "c2")
        assert _is_caregiver_view({"caregiverId": "c1"}, "c1")       # legacy
        assert not _is_caregiver_view({"caregiverIds": ["c1"]}, "cX")


@pytest.mark.asyncio
async def test_register_event_fans_out_to_all_caregivers(monkeypatch):
    c1, c2 = str(ObjectId()), str(ObjectId())
    patient_id = str(ObjectId())

    db = MagicMock()
    db.users.find_one = AsyncMock(return_value={"name": "Ana", "fcmToken": "tok"})
    inserted = MagicMock()
    inserted.inserted_id = ObjectId()
    collection = MagicMock()
    collection.insert_one = AsyncMock(return_value=inserted)
    db.__getitem__.return_value = collection

    monkeypatch.setattr(PairingService, "get_patient_caregivers", AsyncMock(return_value=[c1, c2]))
    monkeypatch.setattr(
        "src.domains.events.services.send_health_alert_push",
        AsyncMock(return_value={"success_count": 2}),
    )

    svc = BiometricEventService(db)
    doc = await svc.register_biometric_event(
        patient_id=patient_id, event_type="manual_alert", payload={"message": "ayuda"},
    )
    await asyncio.sleep(0)  # let the fire-and-forget push task run

    # Event is stored visible to BOTH caregivers.
    assert doc["caregiverIds"] == [c1, c2]
    collection.insert_one.assert_awaited_once()
    stored = collection.insert_one.await_args.args[0]
    assert stored["caregiverIds"] == [c1, c2]
    assert stored["caregiverId"] == c1
