"""
Tests for account + data deletion (DELETE /user/account).

Covers the cascade in ``delete_user_and_data`` with a mocked DB: owned health
data is removed by ``userId``, the user is unlinked (not deleted) from OTHER
patients' biometric events, pairings on both sides are removed, and the user
document itself is deleted.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId

from src.domains.user.routes import (
    delete_user_and_data,
    _USER_OWNED_COLLECTIONS,
    _USER_MULTIFIELD_COLLECTIONS,
)


def _coll_mock(deleted: int = 1, modified: int = 1) -> MagicMock:
    m = MagicMock()
    dm = MagicMock(); dm.deleted_count = deleted
    um = MagicMock(); um.modified_count = modified
    do = MagicMock(); do.deleted_count = deleted
    m.delete_many = AsyncMock(return_value=dm)
    m.update_many = AsyncMock(return_value=um)
    m.delete_one = AsyncMock(return_value=do)
    return m


def _make_db():
    """db[name] (subscript) memoized; db.pairings/.biometric_events/.users as attrs."""
    subscript = {}

    def getitem(name):
        return subscript.setdefault(name, _coll_mock())

    db = MagicMock()
    db.__getitem__.side_effect = getitem
    db.pairings = _coll_mock(deleted=2)
    db.biometric_events = _coll_mock(deleted=3, modified=1)
    db.users = _coll_mock(deleted=1)
    return db, subscript


@pytest.mark.asyncio
async def test_owned_collections_deleted_by_user_id():
    uid = str(ObjectId())
    db, subscript = _make_db()

    await delete_user_and_data(db, uid)

    for coll in _USER_OWNED_COLLECTIONS:
        assert coll in subscript, f"{coll} was never touched"
        subscript[coll].delete_many.assert_awaited_once_with({"userId": uid})


@pytest.mark.asyncio
async def test_multifield_collections_deleted_by_or():
    uid = str(ObjectId())
    db, subscript = _make_db()

    await delete_user_and_data(db, uid)

    for coll, fields in _USER_MULTIFIELD_COLLECTIONS.items():
        flt = subscript[coll].delete_many.await_args.args[0]
        assert flt == {"$or": [{f: uid} for f in fields]}


@pytest.mark.asyncio
async def test_pairings_deleted_both_sides():
    uid = str(ObjectId())
    db, _ = _make_db()

    await delete_user_and_data(db, uid)

    db.pairings.delete_many.assert_awaited_once_with(
        {"$or": [{"patientId": uid}, {"caregiverId": uid}]}
    )


@pytest.mark.asyncio
async def test_biometric_events_owned_deleted_but_caregiver_only_unlinked():
    uid = str(ObjectId())
    db, _ = _make_db()

    await delete_user_and_data(db, uid)

    # Own events (as patient) are deleted...
    db.biometric_events.delete_many.assert_awaited_once_with({"patientId": uid})
    # ...but events of OTHER patients are only unlinked, never deleted.
    pull_call = db.biometric_events.update_many.await_args_list[0]
    flt, update = pull_call.args
    assert flt == {"$or": [{"caregiverIds": uid}, {"caregiverId": uid}]}
    assert update == {"$pull": {"caregiverIds": uid, "readByCaregivers": uid}}


@pytest.mark.asyncio
async def test_user_document_deleted_and_summary_returned():
    uid = str(ObjectId())
    db, _ = _make_db()

    summary = await delete_user_and_data(db, uid)

    db.users.delete_one.assert_awaited_once_with({"_id": ObjectId(uid)})
    assert summary["users"] == 1
    assert summary["pairings"] == 2
    assert summary["biometric_events_owned"] == 3
    # every owned + multifield collection is represented in the summary
    for coll in _USER_OWNED_COLLECTIONS + list(_USER_MULTIFIELD_COLLECTIONS):
        assert coll in summary
