from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status, Body

from src._config.logger import get_logger
from src._config.settings import settings
from src.core.database import get_database
from src.core.security import get_password_hash, verify_password, create_token
from src.domains.sense.schemas import (
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    DeviceTokenRequest,
    DeviceTokenResponse,
    DeviceListResponse,
    DeviceListItem,
    AlertsResponse,
    AlertAckRequest,
    AlertAckResponse,
    CreateAlertRequest,
    CreateAlertResponse,
    DeviceEventsRequest,
    DeviceEventsResponse,
    HeartbeatRequest,
    HeartbeatResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["sense-devices"])


async def _get_device_by_token(
    authorization: Optional[str], db, device_id: Optional[str] = None
):
    # En local/dev: si no hay token pero sí device_id en la ruta, usar ese dispositivo
    if settings.DEBUG and not authorization and device_id:
        try:
            device = await db.devices.find_one({"_id": ObjectId(device_id)})
            if device:
                return device
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="device not found"
            )
        except (TypeError, ValueError, InvalidId):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid device_id: must be a 24-character hex string",
            )

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="no token provided"
        )
    try:
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            raise ValueError("invalid scheme")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid authorization header format",
        )

    device = await db.devices.find_one({"access_token": token})
    if not device:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid token"
        )

    expiry = device.get("access_token_expiry")
    if expiry and datetime.utcnow() > expiry:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="token expired. Use /v1/devices/token to reauthenticate.",
        )

    return device


async def verify_device_token(
    authorization: Optional[str] = Header(None), db=Depends(get_database)
) -> str:
    """
    Returns the string device_id for the authenticated device.
    """
    device = await _get_device_by_token(authorization, db)
    return str(device["_id"])


@router.get(
    "/devices",
    response_model=DeviceListResponse,
)
async def list_devices(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, alias="status"),
    db=Depends(get_database),
):
    """
    List all registered Sense devices. Returns only safe fields (no secrets or tokens).
    Optional query: status=active|suspended|decommissioned.
    """
    query = {}
    if status_filter:
        query["status"] = status_filter

    total = await db.devices.count_documents(query)
    # Project only safe fields (_id is always included unless excluded)
    projection = {
        "hardware_id": 1,
        "device_model": 1,
        "software_version": 1,
        "status": 1,
        "registered_at": 1,
        "last_seen_at": 1,
        "locale": 1,
        "time_zone": 1,
        "os_version": 1,
    }
    cursor = (
        db.devices.find(query, projection)
        .sort("registered_at", -1)
        .skip(offset)
        .limit(limit)
    )

    devices = []
    async for doc in cursor:
        devices.append(
            DeviceListItem(
                device_id=str(doc["_id"]),
                hardware_id=doc.get("hardware_id", ""),
                device_model=doc.get("device_model", ""),
                software_version=doc.get("software_version", ""),
                status=doc.get("status", "active"),
                registered_at=doc.get("registered_at"),
                last_seen_at=doc.get("last_seen_at"),
                locale=doc.get("locale"),
                time_zone=doc.get("time_zone"),
                os_version=doc.get("os_version"),
            )
        )

    return DeviceListResponse(
        devices=devices,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/devices/register",
    response_model=DeviceRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_device(
    body: DeviceRegistrationRequest = Body(...), db=Depends(get_database)
):
    """
    Register a new Sense edge device.
    """
    # TODO: validate provisioning_code against households once that model exists.

    existing = await db.devices.find_one({"hardware_id": body.hardware_id})
    if existing:
        logger.info("Device with hardware_id %s already registered", body.hardware_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="device with this hardware_id already registered",
        )

    device_secret = create_token()
    hashed_secret = get_password_hash(device_secret)

    access_token = create_token()
    access_token_expiry = datetime.utcnow() + timedelta(hours=1)

    doc = {
        "hardware_id": body.hardware_id,
        "device_model": body.device_model,
        "software_version": body.software_version,
        "locale": body.locale,
        "time_zone": body.time_zone,
        "device_secret_hash": hashed_secret,
        "access_token": access_token,
        "access_token_expiry": access_token_expiry,
        "status": "active",
        "registered_at": datetime.utcnow(),
        "last_seen_at": None,
    }

    result = await db.devices.insert_one(doc)
    device_id = str(result.inserted_id)

    # For now, no real patient linkage – return None context.
    return DeviceRegistrationResponse(
        device_id=device_id,
        device_secret=device_secret,
        access_token=access_token,
        access_token_expires_in=3600,
        patient_context=None,
    )


@router.post("/devices/token", response_model=DeviceTokenResponse)
async def device_token(
    body: DeviceTokenRequest = Body(...), db=Depends(get_database)
):
    """
    Issue a short-lived access token for an existing device.
    """
    if body.grant_type != "device_credentials":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported grant_type"
        )

    try:
        oid = ObjectId(body.device_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid device_id"
        )

    device = await db.devices.find_one({"_id": oid})
    if not device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    if not verify_password(body.device_secret, device["device_secret_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    access_token = create_token()
    expiry = datetime.utcnow() + timedelta(hours=1)

    await db.devices.update_one(
        {"_id": oid},
        {"$set": {"access_token": access_token, "access_token_expiry": expiry}},
    )

    return DeviceTokenResponse(access_token=access_token, expires_in=3600)


@router.get(
    "/devices/{device_id}/alerts",
    response_model=AlertsResponse,
)
async def poll_alerts(
    device_id: str,
    cursor: Optional[str] = Query(None),
    since_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    severity: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    db=Depends(get_database),
):
    """
    Poll alerts for the given device. At-least-once delivery with cursor-based pagination.
    """
    device = await _get_device_by_token(authorization, db, device_id=device_id)
    if str(device["_id"]) != device_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    query: dict = {"device_id": device_id}

    if severity:
        query["severity"] = severity

    if cursor:
        try:
            query["_id"] = {"$gt": ObjectId(cursor)}
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="invalid cursor"
            )
    elif since_id:
        try:
            query["_id"] = {"$gt": ObjectId(since_id)}
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="invalid since_id"
            )

    docs_cursor = (
        db.alerts.find(query)
        .sort("_id", 1)
        .limit(limit + 1)  # fetch one extra to determine has_more
    )

    docs = [doc async for doc in docs_cursor]
    has_more = len(docs) > limit
    if has_more:
        docs = docs[:limit]

    alerts = []
    next_cursor: Optional[str] = None

    for doc in docs:
        next_cursor = str(doc["_id"])
        alerts.append(
            {
                "alert_id": doc.get("alert_id", str(doc["_id"])),
                "patient_id": doc.get("patient_id", ""),
                "type": doc.get("type", ""),
                "severity": doc.get("severity", "info"),
                "status": doc.get("status", "pending"),
                "created_at": doc.get("created_at", datetime.utcnow()),
                "valid_until": doc.get("valid_until"),
                "title": doc.get("title", ""),
                "body": doc.get("body", ""),
                "guidance": doc.get("guidance"),
                "escalation": doc.get("escalation"),
                "cause": doc.get("cause"),
            }
        )

    return AlertsResponse(
        alerts=alerts,
        next_cursor=next_cursor,
        has_more=has_more,
        server_time=datetime.utcnow(),
    )


@router.post(
    "/devices/{device_id}/alerts",
    response_model=CreateAlertResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_alert(
    device_id: str,
    body: CreateAlertRequest = Body(...),
    db=Depends(get_database),
):
    """
    Create a new alert for a device. Specify the cause (causa) of the alert.
    Typically used by the backend/analytics; no device token required.
    """
    try:
        oid = ObjectId(device_id)
    except (TypeError, ValueError, InvalidId):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid device_id: must be a 24-character hex string",
        )
    device = await db.devices.find_one({"_id": oid})
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="device not found"
        )

    now = datetime.utcnow()
    doc = {
        "device_id": device_id,
        "patient_id": body.patient_id or "",
        "type": body.type,
        "severity": body.severity,
        "status": "pending",
        "created_at": now,
        "valid_until": body.valid_until,
        "title": body.title,
        "body": body.body,
        "guidance": body.guidance.model_dump(),
        "escalation": body.escalation.model_dump() if body.escalation else None,
        "cause": body.cause,
    }
    result = await db.alerts.insert_one(doc)
    alert_id = str(result.inserted_id)

    return CreateAlertResponse(
        alert_id=alert_id,
        device_id=device_id,
        cause=body.cause,
        status="pending",
        created_at=now,
    )


@router.post(
    "/devices/{device_id}/alerts/ack",
    response_model=AlertAckResponse,
)
async def acknowledge_alerts(
    device_id: str,
    body: AlertAckRequest = Body(...),
    authorization: Optional[str] = Header(None),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db=Depends(get_database),
):
    """
    Acknowledge alerts for a device. Idempotent via optional Idempotency-Key.
    """
    device = await _get_device_by_token(authorization, db, device_id=device_id)
    if str(device["_id"]) != device_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    duplicate = False

    if idempotency_key:
        key_doc = await db.device_ack_keys.find_one(
            {"device_id": device_id, "key": idempotency_key}
        )
        if key_doc:
            duplicate = True
            accepted_ids = key_doc.get("accepted_alert_ids", [])
            server_cursor = key_doc.get("server_cursor")
            return AlertAckResponse(
                accepted_alert_ids=accepted_ids,
                duplicate=True,
                server_cursor=server_cursor,
            )

    accepted_ids = []
    for ack in body.acks:
        await db.device_alert_deliveries.update_one(
            {"device_id": device_id, "alert_id": ack.alert_id},
            {
                "$set": {
                    "device_id": device_id,
                    "alert_id": ack.alert_id,
                    "status": ack.status,
                    "failure_reason": ack.failure_reason,
                    "updated_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )
        accepted_ids.append(ack.alert_id)

    server_cursor = body.up_to_cursor

    if idempotency_key:
        await db.device_ack_keys.update_one(
            {"device_id": device_id, "key": idempotency_key},
            {
                "$set": {
                    "device_id": device_id,
                    "key": idempotency_key,
                    "accepted_alert_ids": accepted_ids,
                    "server_cursor": server_cursor,
                    "created_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

    return AlertAckResponse(
        accepted_alert_ids=accepted_ids,
        duplicate=duplicate,
        server_cursor=server_cursor,
    )


@router.post(
    "/devices/{device_id}/events",
    response_model=DeviceEventsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_events(
    device_id: str,
    body: DeviceEventsRequest = Body(...),
    authorization: Optional[str] = Header(None),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db=Depends(get_database),
):
    """
    Post a batch of device events. Idempotent via Idempotency-Key and event_ids.
    """
    device = await _get_device_by_token(authorization, db, device_id=device_id)
    if str(device["_id"]) != device_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    duplicate = False
    if idempotency_key:
        key_doc = await db.device_event_keys.find_one(
            {"device_id": device_id, "key": idempotency_key}
        )
        if key_doc:
            duplicate = True
            accepted_ids = key_doc.get("accepted_event_ids", [])
            return DeviceEventsResponse(
                accepted_event_ids=accepted_ids, duplicate=True
            )

    accepted_ids = []
    for event in body.events:
        # Deduplicate per (device_id, event_id)
        existing = await db.device_events.find_one(
            {"device_id": device_id, "event_id": event.event_id}
        )
        if existing:
            accepted_ids.append(event.event_id)
            continue

        doc = {
            "device_id": device_id,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "alert_id": event.alert_id,
            "command_id": event.command_id,
            "payload": event.payload,
            "received_at": datetime.utcnow(),
        }
        await db.device_events.insert_one(doc)
        accepted_ids.append(event.event_id)

    if idempotency_key:
        await db.device_event_keys.update_one(
            {"device_id": device_id, "key": idempotency_key},
            {
                "$set": {
                    "device_id": device_id,
                    "key": idempotency_key,
                    "accepted_event_ids": accepted_ids,
                    "created_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

    return DeviceEventsResponse(accepted_event_ids=accepted_ids, duplicate=duplicate)


@router.post(
    "/devices/{device_id}/heartbeat",
    response_model=HeartbeatResponse,
)
async def heartbeat(
    device_id: str,
    body: HeartbeatRequest = Body(...),
    authorization: Optional[str] = Header(None),
    db=Depends(get_database),
):
    """
    Record a device heartbeat and basic health metrics.
    """
    device = await _get_device_by_token(authorization, db, device_id=device_id)
    if str(device["_id"]) != device_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    hb_doc = {
        "device_id": device_id,
        "timestamp": body.timestamp,
        "uptime_seconds": body.uptime_seconds,
        "software_version": body.software_version,
        "os_version": body.os_version,
        "network": body.network.model_dump() if body.network else None,
        "audio": body.audio.model_dump() if body.audio else None,
        "storage": body.storage.model_dump() if body.storage else None,
        "pending_error_code": body.pending_error_code,
        "received_at": datetime.utcnow(),
    }

    await db.device_heartbeats.insert_one(hb_doc)

    await db.devices.update_one(
        {"_id": device["_id"]},
        {
            "$set": {
                "last_seen_at": datetime.utcnow(),
                "software_version": body.software_version,
                "os_version": body.os_version,
            }
        },
    )

    return HeartbeatResponse(
        server_time=datetime.utcnow(),
        heartbeat_interval_hint_seconds=300,
        config_version=device.get("config_version"),
    )

