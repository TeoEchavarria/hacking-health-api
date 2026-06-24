"""
One-time cleanup: enforce the "one caregiver → one patient" rule on EXISTING
data.

A bug let `validate_pairing_code` activate a new caregiver pairing without
ending the caregiver's previous one, so some caregiver accounts ended up with
several active pairings at once. As a result they kept seeing the previous
patient's notifications and medications.

This script finds every caregiver with more than one active pairing, keeps the
most recently activated one, and marks the rest as ``status="ended"`` (same
state the fixed pairing flow now sets — excluded from all active-only queries).

Safe by default: prints what it WOULD do (dry-run). Pass --apply to write.

Usage:
    cd hacking-health-api
    python -m scripts.cleanup_duplicate_caregiver_pairings              # dry-run, all caregivers
    python -m scripts.cleanup_duplicate_caregiver_pairings --apply      # actually end duplicates
    python -m scripts.cleanup_duplicate_caregiver_pairings --email cuidadora@example.com --apply

Reads MONGO_URI / MONGO_DB from src._config.settings (same env as the API).
"""
import argparse
import asyncio
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from src._config.settings import settings


def _activated_key(pairing: dict):
    """Sort key: most recently activated first; fall back to created/_id time."""
    return (
        pairing.get("activatedAt")
        or pairing.get("createdAt")
        or pairing.get("_id").generation_time
    )


async def cleanup(apply: bool, email: Optional[str]) -> None:
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]

    # Optionally restrict to a single caregiver (by email).
    caregiver_filter = None
    if email:
        user = await db.users.find_one({"email": email})
        if not user:
            print(f"❌ No user found with email {email}")
            client.close()
            return
        caregiver_filter = str(user["_id"])
        print(f"Targeting caregiver {email} ({caregiver_filter})\n")

    match: dict = {"status": "active"}
    if caregiver_filter:
        match["caregiverId"] = caregiver_filter

    # Group active pairings by caregiver, keep only caregivers with > 1.
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$caregiverId", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
        {"$match": {"count": {"$gt": 1}}},
    ]
    groups = await db.pairings.aggregate(pipeline).to_list(length=10000)

    if not groups:
        print("✅ No caregiver has more than one active pairing. Nothing to do.")
        client.close()
        return

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== {mode}: {len(groups)} caregiver(s) with duplicate active pairings ===\n")

    total_ended = 0
    for group in groups:
        caregiver_id = group["_id"]
        pairings = await db.pairings.find(
            {"caregiverId": caregiver_id, "status": "active"}
        ).to_list(length=100)
        pairings.sort(key=_activated_key, reverse=True)

        keep = pairings[0]
        drop = pairings[1:]

        caregiver = None
        try:
            caregiver = await db.users.find_one({"_id": ObjectId(caregiver_id)})
        except Exception:
            pass
        cg_name = caregiver.get("name") if caregiver else "?"

        print(f"Caregiver {cg_name} ({caregiver_id}): {len(pairings)} active → keep 1, end {len(drop)}")
        print(f"  KEEP  patient={keep.get('patientName')!r} ({keep.get('patientId')})  activatedAt={keep.get('activatedAt')}")
        for p in drop:
            print(f"  END   patient={p.get('patientName')!r} ({p.get('patientId')})  activatedAt={p.get('activatedAt')}  _id={p.get('_id')}")

        if apply and drop:
            res = await db.pairings.update_many(
                {"_id": {"$in": [p["_id"] for p in drop]}},
                {
                    "$set": {
                        "status": "ended",
                        "endedAt": datetime.now(timezone.utc),
                        "endedReason": "cleanup_duplicate_caregiver_pairing",
                    }
                },
            )
            total_ended += res.modified_count
        else:
            total_ended += len(drop)
        print()

    if apply:
        print(f"✅ Ended {total_ended} duplicate pairing(s).")
    else:
        print(f"ℹ️  DRY-RUN: would end {total_ended} duplicate pairing(s). Re-run with --apply to write.")

    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="End duplicate active caregiver pairings (keep most recent).")
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run).")
    parser.add_argument("--email", help="Only clean up this caregiver (by email).")
    args = parser.parse_args()
    asyncio.run(cleanup(args.apply, args.email))


if __name__ == "__main__":
    main()
