"""
Tests for caregiver access control & /caregiver/* endpoints.

Validates the security requirements:
  1. Caregiver with active pairing  → 200 ✓
  2. Caregiver without pairing       → 403
  3. Patient accessing another patient's data → 403 (via assert_data_access)
  4. Token without role              → 401 / still works because role isn't enforced at auth layer;
                                       this test asserts an unsigned/malformed token is rejected
  5. Pairing with status != "active" → 403
  6. /caregiver/patients lists only active caregiver pairings

We exercise authorization at the service/helper layer with an AsyncMock'd db
rather than spinning a real Mongo. Endpoint integration is covered through
the FastAPI TestClient with dependency overrides.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from bson.objectid import ObjectId

from src.main import app
from src.core.database import get_database, db
from src.core.authorization import (
    require_caregiver_access,
    assert_data_access,
)
from src.core import jwt as jwt_module
from src.domains.auth.routes import verify_token_jwt
from src._config.settings import settings


# Valid 24-hex-char ObjectIds for the tests
CAREGIVER_ID = "507f1f77bcf86cd799439011"
PATIENT_ID = "507f1f77bcf86cd799439012"
OTHER_PATIENT_ID = "507f1f77bcf86cd799439013"


# -----------------------------------------------------------------------------
# Helper-level tests (authorization.py)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_caregiver_access_with_active_pairing_returns_patient():
    """Caregiver with active pairing → returns safe patient projection."""
    mock_db = AsyncMock()
    mock_db.users.find_one = AsyncMock(return_value={
        "_id": ObjectId(PATIENT_ID),
        "name": "Carmen",
        "email": "carmen@example.com",       # must NOT leak into response
        "password": "secret_hash",            # must NOT leak
        "profile_picture": "https://x/y.jpg",
    })
    mock_db.pairings.find_one = AsyncMock(return_value={
        "_id": ObjectId(),
        "caregiverId": CAREGIVER_ID,
        "patientId": PATIENT_ID,
        "status": "active",
    })

    result = await require_caregiver_access(PATIENT_ID, CAREGIVER_ID, mock_db)

    assert result["patient_id"] == PATIENT_ID
    assert result["name"] == "Carmen"
    assert result["profile_picture"] == "https://x/y.jpg"
    assert "email" not in result
    assert "password" not in result


@pytest.mark.asyncio
async def test_require_caregiver_access_without_pairing_raises_403():
    """Caregiver with no pairing → 403."""
    mock_db = AsyncMock()
    mock_db.users.find_one = AsyncMock(return_value={
        "_id": ObjectId(PATIENT_ID),
        "name": "Carmen",
    })
    mock_db.pairings.find_one = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await require_caregiver_access(PATIENT_ID, CAREGIVER_ID, mock_db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_caregiver_access_with_revoked_pairing_raises_403():
    """status != 'active' pairing must NOT grant access (query already filters)."""
    mock_db = AsyncMock()
    mock_db.users.find_one = AsyncMock(return_value={
        "_id": ObjectId(PATIENT_ID),
        "name": "Carmen",
    })
    # Repository query filters {status: "active"} so a revoked pairing returns None
    mock_db.pairings.find_one = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await require_caregiver_access(PATIENT_ID, CAREGIVER_ID, mock_db)
    assert exc.value.status_code == 403
    # Verify the query was filtered by status="active"
    call_kwargs = mock_db.pairings.find_one.call_args
    query = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("filter")
    assert query["status"] == "active"


@pytest.mark.asyncio
async def test_require_caregiver_access_self_access_raises_403():
    """requester == patient on caregiver-only endpoint → 403 (own-data NOT allowed here)."""
    mock_db = AsyncMock()
    mock_db.users.find_one = AsyncMock(return_value={
        "_id": ObjectId(PATIENT_ID),
        "name": "Carmen",
    })

    with pytest.raises(HTTPException) as exc:
        await require_caregiver_access(PATIENT_ID, PATIENT_ID, mock_db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_caregiver_access_unknown_patient_raises_404():
    """Patient does not exist → 404."""
    mock_db = AsyncMock()
    mock_db.users.find_one = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await require_caregiver_access(PATIENT_ID, CAREGIVER_ID, mock_db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_caregiver_access_invalid_patient_id_raises_404():
    """patient_id not a valid ObjectId → 404 (not 500)."""
    mock_db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await require_caregiver_access("not-an-objectid", CAREGIVER_ID, mock_db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_assert_data_access_allows_own_data():
    """A user accessing their own data is allowed (no pairing query needed)."""
    mock_db = AsyncMock()
    # Should not raise
    await assert_data_access(mock_db, PATIENT_ID, PATIENT_ID)


@pytest.mark.asyncio
async def test_assert_data_access_blocks_other_patient():
    """A patient cannot read another patient's data."""
    mock_db = AsyncMock()
    mock_db.pairings.find_one = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await assert_data_access(mock_db, PATIENT_ID, OTHER_PATIENT_ID)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_assert_data_access_allows_caregiver_with_pairing():
    """Caregiver with active pairing → no exception."""
    mock_db = AsyncMock()
    mock_db.pairings.find_one = AsyncMock(return_value={
        "caregiverId": CAREGIVER_ID,
        "patientId": PATIENT_ID,
        "status": "active",
    })
    await assert_data_access(mock_db, CAREGIVER_ID, PATIENT_ID)


# -----------------------------------------------------------------------------
# JWT role tests
# -----------------------------------------------------------------------------

def test_jwt_includes_role_when_provided():
    """create_access_token must embed role in payload when supplied."""
    token = jwt_module.create_access_token(
        user_id=CAREGIVER_ID,
        email="c@example.com",
        role="caregiver",
    )
    payload = jwt_module.verify_access_token(token)
    assert payload["role"] == "caregiver"
    assert payload["sub"] == CAREGIVER_ID


def test_jwt_omits_role_when_not_provided():
    """role is optional — when omitted, payload has no role field."""
    token = jwt_module.create_access_token(user_id=CAREGIVER_ID)
    payload = jwt_module.verify_access_token(token)
    assert "role" not in payload


def test_malformed_token_is_rejected():
    """Unsigned / malformed token must fail verification."""
    from src.core.jwt import verify_access_token, TokenInvalidError
    with pytest.raises(TokenInvalidError):
        verify_access_token("not.a.valid.jwt")


# -----------------------------------------------------------------------------
# Endpoint integration tests (TestClient)
# -----------------------------------------------------------------------------

@pytest.fixture
def caregiver_client(monkeypatch):
    """
    TestClient with verify_token_jwt overridden to return CAREGIVER_ID,
    and get_database overridden with a mock db that allows attribute access.
    """
    # Force DEBUG=False so the auth dep doesn't bypass to dev user
    monkeypatch.setattr(settings, "DEBUG", False)

    # Use MagicMock for the DB (sync attribute access) and explicitly set
    # AsyncMock on methods that the service code awaits. AsyncMock as the root
    # makes child attribute reassignment unreliable.
    mock_db = MagicMock()
    mock_db.pairings = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=None)
    mock_db.pairings.find_one = AsyncMock(return_value=None)
    mock_db.pairings.find = MagicMock(return_value=_async_cursor([]))
    mock_db.blood_pressure_readings = MagicMock()
    mock_db.blood_pressure_readings.find = MagicMock(return_value=_async_cursor([]))
    mock_db.health_metrics = MagicMock()
    mock_db.health_metrics.find = MagicMock(return_value=_async_cursor([]))

    # Some services use subscript access: db["pairings"] instead of db.pairings.
    # Route both to the same collection mocks.
    def _getitem(name):
        return getattr(mock_db, name)
    mock_db.__getitem__.side_effect = _getitem

    def override_db():
        return mock_db

    def override_auth():
        return CAREGIVER_ID

    app.dependency_overrides[get_database] = override_db
    app.dependency_overrides[verify_token_jwt] = override_auth

    db.connect = MagicMock()
    db.close = MagicMock()

    # NOTE: do not use `with TestClient(app) as c:` because the context manager
    # triggers FastAPI's startup lifespan, which tries to connect to MongoDB.
    c = TestClient(app)
    c.mock_db = mock_db
    try:
        yield c
    finally:
        app.dependency_overrides.clear()


def test_caregiver_patients_list_returns_active_pairings(caregiver_client):
    """GET /caregiver/patients returns only this caregiver's active patients."""
    pairing_oid = ObjectId()
    caregiver_client.mock_db.pairings.find = MagicMock(return_value=_async_cursor([
        {
            "_id": pairing_oid,
            "patientId": PATIENT_ID,
            "patientName": "Carmen",
            "caregiverId": CAREGIVER_ID,
            "status": "active",
        }
    ]))
    caregiver_client.mock_db.users.find_one = AsyncMock(return_value={
        "_id": ObjectId(PATIENT_ID),
        "name": "Carmen",
        "profile_picture": None,
    })

    resp = caregiver_client.get("/caregiver/patients")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["patients"][0]["patient_id"] == PATIENT_ID
    assert data["patients"][0]["name"] == "Carmen"
    # No sensitive fields
    assert "email" not in data["patients"][0]
    assert "password" not in data["patients"][0]


def test_caregiver_bp_history_403_when_no_pairing(caregiver_client):
    """Caregiver without an active pairing → 403."""
    caregiver_client.mock_db.users.find_one = AsyncMock(return_value={
        "_id": ObjectId(PATIENT_ID),
        "name": "Carmen",
    })
    caregiver_client.mock_db.pairings.find_one = AsyncMock(return_value=None)

    resp = caregiver_client.get(f"/caregiver/patients/{PATIENT_ID}/history/bp")
    assert resp.status_code == 403


def test_caregiver_steps_history_404_when_patient_missing(caregiver_client):
    """Unknown patient_id → 404."""
    caregiver_client.mock_db.users.find_one = AsyncMock(return_value=None)
    resp = caregiver_client.get(f"/caregiver/patients/{PATIENT_ID}/history/steps")
    assert resp.status_code == 404


def test_caregiver_bp_history_response_is_flat_list(caregiver_client):
    """
    Regression test: `readings` in the JSON response must be a top-level
    LIST, not a nested dict. Previously the route was forwarding the full
    service dict ({patient_id, patient_name, readings:[...], count})
    under the `readings` key, which broke the Android client.
    """
    caregiver_client.mock_db.users.find_one = AsyncMock(return_value={
        "_id": ObjectId(PATIENT_ID),
        "name": "Carmen",
    })
    caregiver_client.mock_db.pairings.find_one = AsyncMock(return_value={
        "_id": ObjectId(),
        "caregiverId": CAREGIVER_ID,
        "patientId": PATIENT_ID,
        "status": "active",
    })
    # Mock blood_pressure_readings cursor with one document.
    caregiver_client.mock_db.blood_pressure_readings.find = MagicMock(
        return_value=_async_cursor([
            {
                "_id": ObjectId(),
                "userId": PATIENT_ID,
                "systolic": 122,
                "diastolic": 80,
                "pulse": 72,
                "timestamp": "2026-05-19T10:00:00",
                "date": "2026-05-19",
                "source": "voice",
                "stage": "normal",
                "severity": "normal",
                "crisis_flag": False,
            }
        ])
    )

    resp = caregiver_client.get(f"/caregiver/patients/{PATIENT_ID}/history/bp")
    assert resp.status_code == 200
    data = resp.json()
    # readings MUST be a JSON array
    assert isinstance(data["readings"], list), \
        f"Expected list, got {type(data['readings']).__name__}: {data['readings']}"
    assert data["count"] == len(data["readings"])
    # patient projection still sanitised
    assert "email" not in data["patient"]
    assert "password" not in data["patient"]
    # If at least one reading is returned its shape exposes the BP fields.
    if data["readings"]:
        r = data["readings"][0]
        assert "systolic" in r
        assert "diastolic" in r


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _async_cursor(items):
    """Build a MagicMock that mimics a Motor cursor: .sort().to_list() / .find()."""
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=items)
    return cursor
