"""
Diagnostic script: dump every blood pressure reading and biometric event
for a given patient (looked up by email), so we can answer "did the
caregiver lose a reading or was it never saved in the first place?".

Usage:
    cd hacking-health-api
    python -m scripts.diagnose_patient_bp carmencita5010@gmail.com
    # Optional: only today
    python -m scripts.diagnose_patient_bp carmencita5010@gmail.com --today

Reads MONGO_URI / MONGO_DB from src._config.settings (i.e. honours the
same env you use for the API).
"""
import argparse
import asyncio
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from src._config.settings import settings


async def diagnose(email: str, only_today: bool) -> None:
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]

    user = await db.users.find_one({"email": email})
    if not user:
        print(f"❌ No user found with email {email}")
        return

    user_id = str(user["_id"])
    print("\n=== Patient ===")
    print(f"  name:      {user.get('name')}")
    print(f"  email:     {email}")
    print(f"  _id:       {user_id}")
    print(f"  role:      {user.get('role')}")

    # Active pairing
    pairing = await db.pairings.find_one({"patientId": user_id, "status": "active"})
    if pairing:
        caregiver = await db.users.find_one({"_id": pairing["caregiverId"]}) if pairing.get("caregiverId") else None
        print("\n=== Active pairing ===")
        print(f"  caregiverId:   {pairing.get('caregiverId')}")
        print(f"  caregiverName: {caregiver.get('name') if caregiver else '?'}")
    else:
        print("\n⚠️  No active pairing")

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bp_query: dict = {"userId": user_id}
    if only_today:
        bp_query["date"] = today_str

    bp_cursor = db.blood_pressure_readings.find(bp_query).sort("timestamp", -1)
    bp_docs = await bp_cursor.to_list(length=500)

    print(f"\n=== blood_pressure_readings  (today={today_str}, only_today={only_today}) ===")
    print(f"  total found: {len(bp_docs)}")
    for d in bp_docs:
        print(
            f"  • {d.get('timestamp')}  {d.get('systolic')}/{d.get('diastolic')}"
            f"  src={d.get('source')!r:>22}  stage={d.get('stage')!r:>22}"
            f"  date={d.get('date')!r}  _id={d.get('_id')}"
        )

    # Biometric events: useful to see how many push notifications fired
    ev_query: dict = {
        "patientId": user_id,
        "type": {"$in": ["voice_measurement", "watch_measurement"]},
    }
    if only_today:
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        ev_query["recordedAt"] = {"$gte": start_of_day}

    ev_cursor = db.biometric_events.find(ev_query).sort("recordedAt", -1)
    ev_docs = await ev_cursor.to_list(length=500)

    print(f"\n=== biometric_events (voice/watch measurements) ===")
    print(f"  total found: {len(ev_docs)}")
    for d in ev_docs:
        payload = d.get("payload", {})
        sys = payload.get("systolic")
        dia = payload.get("diastolic")
        print(
            f"  • {d.get('recordedAt')}  type={d.get('type')!r:>22}  "
            f"sys/dia={sys}/{dia}  severity={d.get('severity')!r}  "
            f"msg={d.get('message')!r}"
        )

    print("\n=== Mismatch analysis ===")
    voice_events = [e for e in ev_docs if e.get("type") == "voice_measurement"]
    voice_with_values = [e for e in voice_events if e.get("payload", {}).get("systolic")]
    voice_readings = [
        d for d in bp_docs
        if (d.get("source") or "").startswith("voice")
    ]
    print(f"  voice_measurement events:           {len(voice_events)}")
    print(f"  voice_measurement events with BP:   {len(voice_with_values)}")
    print(f"  blood_pressure_readings (voice src):{len(voice_readings)}")
    diff = len(voice_with_values) - len(voice_readings)
    if diff > 0:
        print(
            f"  ⚠️  {diff} voice readings were classified+notified but NEVER persisted "
            f"in blood_pressure_readings. The user probably dismissed the confirm dialog "
            f"or the BloodPressureSyncWorker never ran (offline / app killed)."
        )

    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose a patient's BP records")
    parser.add_argument("email", help="Patient email")
    parser.add_argument("--today", action="store_true", help="Only inspect today's data")
    args = parser.parse_args()
    asyncio.run(diagnose(args.email, args.today))


if __name__ == "__main__":
    main()
