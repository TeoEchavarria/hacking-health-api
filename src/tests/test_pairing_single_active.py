"""
Tests for the "one caregiver → one patient" rule and its consequences.

A caregiver may look after only one person at a time. Linking to a new patient
auto-ends the previous pairing, and a caregiver must never see events from a
patient they are no longer linked to. These tests cover, with a mocked DB:

- PairingService._end_other_caregiver_pairings (auto-replace helper)
- validate_pairing_code triggers the auto-replace after activating
- BiometricEventService.get_events_for_user scopes caregiver events to the
  caregiver's CURRENTLY active patients
"""
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId

from src.domains.pairing.services import PairingService
from src.domains.events.services import BiometricEventService


def _mock_db_with_collection():
    collection = MagicMock()
    db = MagicMock()
    db.__getitem__.return_value = collection
    return db, collection


@pytest.mark.asyncio
async def test_end_other_caregiver_pairings_keeps_only_one():
    keep = ObjectId()
    db, collection = _mock_db_with_collection()
    res = MagicMock()
    res.modified_count = 2
    collection.update_many = AsyncMock(return_value=res)

    svc = PairingService(db)
    ended = await svc._end_other_caregiver_pairings(caregiver_id="cg1", keep_pairing_id=keep)

    assert ended == 2
    flt, update = collection.update_many.await_args.args
    # Only this caregiver's OTHER active pairings are targeted.
    assert flt["caregiverId"] == "cg1"
    assert flt["status"] == "active"
    assert flt["_id"] == {"$ne": keep}
    # They are ended (kept out of every active-only query), not deleted.
    assert update["$set"]["status"] == "ended"
    assert update["$set"]["endedReason"] == "replaced_by_new_pairing"


@pytest.mark.asyncio
async def test_end_other_caregiver_pairings_accepts_string_id():
    keep = ObjectId()
    db, collection = _mock_db_with_collection()
    res = MagicMock()
    res.modified_count = 0
    collection.update_many = AsyncMock(return_value=res)

    svc = PairingService(db)
    await svc._end_other_caregiver_pairings(caregiver_id="cg1", keep_pairing_id=str(keep))

    flt, _ = collection.update_many.await_args.args
    # String id is coerced to ObjectId so the $ne actually matches the kept doc.
    assert flt["_id"] == {"$ne": keep}


@pytest.mark.asyncio
async def test_validate_pairing_code_auto_replaces_previous(monkeypatch):
    caregiver_id = str(ObjectId())
    patient_id = str(ObjectId())
    pending_id = ObjectId()

    db, collection = _mock_db_with_collection()
    db.users.find_one = AsyncMock(return_value={"_id": ObjectId(caregiver_id), "name": "Ana"})
    pending = {
        "_id": pending_id,
        "patientId": patient_id,
        "patientName": "Bob",
        "status": "pending",
        "code": "123456",
        "expiresAt": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    # 1st find_one → pending code; 2nd find_one → duplicate check (none).
    collection.find_one = AsyncMock(side_effect=[pending, None])
    collection.update_one = AsyncMock()

    svc = PairingService(db)
    end_spy = AsyncMock(return_value=1)
    monkeypatch.setattr(svc, "_end_other_caregiver_pairings", end_spy)

    result = await svc.validate_pairing_code(code="123456", caregiver_id=caregiver_id)

    assert result["success"] is True
    # The previous pairing(s) of this caregiver are auto-ended, keeping the new one.
    end_spy.assert_awaited_once()
    assert end_spy.await_args.kwargs["caregiver_id"] == caregiver_id
    assert end_spy.await_args.kwargs["keep_pairing_id"] == pending_id


@pytest.mark.asyncio
async def test_get_events_scopes_caregiver_to_active_patients(monkeypatch):
    user_id = str(ObjectId())
    active_patient = str(ObjectId())

    monkeypatch.setattr(
        PairingService, "get_caregiver_patients",
        AsyncMock(return_value=[active_patient]),
    )

    db, collection = _mock_db_with_collection()
    collection.count_documents = AsyncMock(return_value=0)
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    collection.find.return_value = cursor

    svc = BiometricEventService(db)
    await svc.get_events_for_user(user_id)

    query = collection.count_documents.await_args.args[0]
    or_clauses = query["$or"]
    # The user always sees their OWN events (as patient).
    assert {"patientId": user_id} in or_clauses
    # The caregiver branch is restricted to currently-active patients.
    caregiver_clauses = [c for c in or_clauses if isinstance(c.get("patientId"), dict)]
    assert len(caregiver_clauses) == 1
    assert caregiver_clauses[0]["patientId"] == {"$in": [active_patient]}
    assert {"caregiverId": user_id} in caregiver_clauses[0]["$or"]
    assert {"caregiverIds": user_id} in caregiver_clauses[0]["$or"]


@pytest.mark.asyncio
async def test_get_events_no_active_patients_only_own(monkeypatch):
    """A caregiver with no active patient sees only their own (patient) events."""
    user_id = str(ObjectId())
    monkeypatch.setattr(
        PairingService, "get_caregiver_patients",
        AsyncMock(return_value=[]),
    )

    db, collection = _mock_db_with_collection()
    collection.count_documents = AsyncMock(return_value=0)
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    collection.find.return_value = cursor

    svc = BiometricEventService(db)
    await svc.get_events_for_user(user_id)

    query = collection.count_documents.await_args.args[0]
    assert query["$or"] == [{"patientId": user_id}]
