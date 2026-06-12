"""
Servicios para gestión de medicamentos
"""
from datetime import datetime, date
from typing import Optional, List
from uuid import uuid4
import calendar

from src.domains.medications.models import MedicationDB, MedicationTakeDB
from src._config.logger import get_logger

logger = get_logger(__name__)

PAIRINGS_COLLECTION = "pairings"


class MedicationService:
    """Servicio para gestión de medicamentos"""
    
    def __init__(self, db):
        self.db = db
        self.medications = db.medications
        self.medication_takes = db.medication_takes
    
    async def verify_patient_access(
        self,
        db,
        requester_id: str,
        patient_id: str
    ) -> bool:
        """
        Verifica si el solicitante tiene acceso a los datos del paciente.
        
        Acceso permitido si:
        1. requester_id == patient_id (accede a sus propios datos)
        2. requester es un cuidador activo de este paciente
        """
        # Caso 1: Usuario accediendo a sus propios datos
        if requester_id == patient_id:
            return True
        
        # Caso 2: Verificar si es un cuidador activo
        pairing = await db[PAIRINGS_COLLECTION].find_one({
            "caregiverId": requester_id,
            "patientId": patient_id,
            "status": "active"
        })
        
        if pairing:
            logger.debug(
                f"Caregiver {requester_id} has active pairing with patient {patient_id}"
            )
            return True
        
        logger.warning(
            f"Access denied: User {requester_id} attempted to access "
            f"medications of patient {patient_id} without valid pairing"
        )
        return False
    
    async def get_medication_raw(self, medication_id: str) -> Optional[dict]:
        """
        Obtiene el documento raw de un medicamento (para verificaciones internas).
        """
        return await self.medications.find_one({"_id": medication_id})
    
    async def create_medication(
        self,
        user_id: str,
        name: str,
        dosage: str,
        times: List[str],
        instructions: str,
        medication_type: str
    ) -> dict:
        """Crear un nuevo medicamento"""
        medication_id = str(uuid4())

        document = MedicationDB.create_document(
            medication_id=medication_id,
            user_id=user_id,
            name=name,
            dosage=dosage,
            times=times,
            instructions=instructions,
            medication_type=medication_type
        )

        await self.medications.insert_one(document)
        logger.info(
            f"Created medication {medication_id} for user {user_id} "
            f"with {len(times)} reminder time(s)"
        )

        return MedicationDB.to_response(document)
    
    async def get_medications(self, user_id: str, include_inactive: bool = False) -> List[dict]:
        """Obtener todos los medicamentos de un usuario"""
        query = {"userId": user_id}
        if not include_inactive:
            query["isActive"] = True

        # Sort by the legacy `time` field. New `times` documents have it set
        # to the first scheduled time, so the order remains sensible.
        cursor = self.medications.find(query).sort("time", 1)
        medications = []
        
        async for doc in cursor:
            medications.append(MedicationDB.to_response(doc))
        
        return medications
    
    async def get_medication(self, medication_id: str, user_id: str) -> Optional[dict]:
        """Obtener un medicamento específico"""
        doc = await self.medications.find_one({
            "_id": medication_id,
            "userId": user_id
        })
        
        if doc:
            return MedicationDB.to_response(doc)
        return None
    
    async def update_medication(
        self,
        medication_id: str,
        user_id: str,
        updates: dict
    ) -> Optional[dict]:
        """Actualizar un medicamento"""
        # Build update document
        update_doc = {"$set": {"updatedAt": datetime.utcnow()}}

        if "name" in updates and updates["name"]:
            update_doc["$set"]["name"] = updates["name"]
        if "dosage" in updates:
            update_doc["$set"]["dosage"] = updates["dosage"]
        # Handle times (list) and legacy time (single). When `times` is given
        # it wins; otherwise a legacy `time` payload updates the first slot.
        if "times" in updates and updates["times"] is not None:
            new_times = list(updates["times"])
            update_doc["$set"]["times"] = new_times
            update_doc["$set"]["time"] = new_times[0] if new_times else ""
        elif "time" in updates and updates["time"] is not None:
            update_doc["$set"]["time"] = updates["time"]
            update_doc["$set"]["times"] = [updates["time"]]
        if "instructions" in updates:
            update_doc["$set"]["instructions"] = updates["instructions"]
        if "medication_type" in updates:
            update_doc["$set"]["medicationType"] = updates["medication_type"]
        if "is_active" in updates:
            update_doc["$set"]["isActive"] = updates["is_active"]
        
        result = await self.medications.find_one_and_update(
            {"_id": medication_id, "userId": user_id},
            update_doc,
            return_document=True
        )
        
        if result:
            logger.info(f"Updated medication {medication_id}")
            return MedicationDB.to_response(result)
        return None
    
    async def delete_medication(self, medication_id: str, user_id: str) -> bool:
        """Eliminar un medicamento (soft delete - marcar como inactivo)"""
        result = await self.medications.update_one(
            {"_id": medication_id, "userId": user_id},
            {
                "$set": {
                    "isActive": False,
                    "updatedAt": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Soft deleted medication {medication_id}")
            return True
        return False
    
    async def take_medication(
        self,
        medication_id: str,
        user_id: str,
        taken_at: Optional[datetime] = None,
        notes: Optional[str] = None,
        scheduled_time: Optional[str] = None,
    ) -> Optional[dict]:
        """Registrar la toma de un medicamento

        ``scheduled_time`` ("HH:MM") allows the caller to mark one specific
        scheduled slot as fulfilled. Without it, the take counts toward the
        first unfulfilled slot of the day (legacy behaviour).
        """
        # Verify medication exists and belongs to user
        medication = await self.medications.find_one({
            "_id": medication_id,
            "userId": user_id
        })

        if not medication:
            return None

        take_id = str(uuid4())
        actual_taken_at = taken_at or datetime.utcnow()
        date_str = actual_taken_at.strftime("%Y-%m-%d")

        document = MedicationTakeDB.create_document(
            take_id=take_id,
            medication_id=medication_id,
            user_id=user_id,
            taken_at=actual_taken_at,
            date=date_str,
            notes=notes,
            scheduled_time=scheduled_time,
        )

        await self.medication_takes.insert_one(document)
        logger.info(
            f"Recorded take {take_id} for medication {medication_id}"
            + (f" (slot {scheduled_time})" if scheduled_time else "")
        )

        return MedicationTakeDB.to_response(document)
    
    async def untake_medication(
        self,
        medication_id: str,
        user_id: str,
        date_str: str,
        scheduled_time: Optional[str] = None,
    ) -> bool:
        """Desmarcar la toma de un medicamento de un día específico.

        If ``scheduled_time`` is provided we delete the take registered for
        that exact slot. Otherwise we delete the most recent take of the day
        (legacy behaviour).
        """
        query: dict = {
            "medicationId": medication_id,
            "userId": user_id,
            "date": date_str,
        }
        if scheduled_time:
            query["scheduledTime"] = scheduled_time

        result = await self.medication_takes.find_one_and_delete(
            query,
            sort=[("takenAt", -1)],  # Delete the most recent matching one
        )

        return result is not None
    
    async def get_takes_for_date(
        self,
        user_id: str,
        date_str: str
    ) -> List[dict]:
        """Obtener todas las tomas de un día"""
        cursor = self.medication_takes.find({
            "userId": user_id,
            "date": date_str
        })
        
        takes = []
        async for doc in cursor:
            takes.append(MedicationTakeDB.to_response(doc))
        
        return takes

    async def check_and_notify_missed_doses(
        self,
        patient_id: str,
        medications_with_takes: List[dict],
        grace_minutes: int = 30,
    ) -> None:
        """
        Look at today's medications and, for each scheduled slot whose moment
        + grace period has passed without enough takes recorded, register a
        SINGLE batched MEDICATION_MISSED_BATCH biometric event grouping all
        the medications pending for that slot. The caregiver receives one
        push per (slot, day), not one per pending pill.

        Dedup is enforced via the per-medication `missedAlertsByTime` map
        with key `YYYY-MM-DD:HH:MM` so callers can invoke this method on
        every list refresh without spamming.
        """
        from src.domains.events.services import BiometricEventService
        from src.domains.events.schemas import BiometricEventType

        if not medications_with_takes:
            return

        now = datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")
        event_service = BiometricEventService(self.db)

        # slot -> list of {med_id, name, dosage}
        pending_by_slot: dict = {}

        for item in medications_with_takes:
            med = item.get("medication") or {}
            takes = item.get("takes") or []
            takes_count = len(takes)
            scheduled_times = med.get("times") or (
                [med.get("time")] if med.get("time") else []
            )
            scheduled_times = [t for t in scheduled_times if t and ":" in t]
            if not scheduled_times:
                continue

            med_id = med.get("id") or med.get("_id")
            if not med_id:
                continue

            doc = await self.medications.find_one({"_id": med_id})
            if not doc:
                continue
            missed_map = doc.get("missedAlertsByTime") or {}

            for idx, scheduled in enumerate(sorted(scheduled_times)):
                # If patient already has enough takes to cover slots up to
                # and including this one, skip.
                if takes_count > idx:
                    continue
                try:
                    hh, mm = scheduled.split(":")
                    scheduled_dt = now.replace(
                        hour=int(hh), minute=int(mm), second=0, microsecond=0
                    )
                except Exception:
                    continue

                overdue_minutes = (now - scheduled_dt).total_seconds() / 60
                if overdue_minutes < grace_minutes:
                    continue

                slot_key = f"{today_str}:{scheduled}"
                if missed_map.get(slot_key):
                    continue

                pending_by_slot.setdefault(scheduled, []).append({
                    "med_id": med_id,
                    "name": doc.get("name", ""),
                    "dosage": doc.get("dosage", ""),
                    "slot_key": slot_key,
                })

        # Fire one batch event per slot that has any pending medications.
        for scheduled, entries in pending_by_slot.items():
            if not entries:
                continue
            try:
                await event_service.register_biometric_event(
                    patient_id=patient_id,
                    event_type=BiometricEventType.MEDICATION_MISSED_BATCH.value,
                    payload={
                        "scheduled_time": scheduled,
                        "count": len(entries),
                        "medications": [
                            {
                                "medication_id": e["med_id"],
                                "name": e["name"],
                                "dosage": e["dosage"],
                            }
                            for e in entries
                        ],
                    },
                )
                # Mark dedup on every medication in this batch.
                for e in entries:
                    await self.medications.update_one(
                        {"_id": e["med_id"]},
                        {"$set": {f"missedAlertsByTime.{e['slot_key']}": True}},
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to register missed-dose batch event at "
                    f"{scheduled} for patient {patient_id}: {e}"
                )
    
    async def get_medications_with_today_status(
        self,
        user_id: str,
        target_date: Optional[str] = None
    ) -> List[dict]:
        """Obtener medicamentos con estado de toma del día"""
        date_str = target_date or datetime.utcnow().strftime("%Y-%m-%d")
        
        # Get all active medications
        medications = await self.get_medications(user_id)
        
        # Get today's takes
        takes = await self.get_takes_for_date(user_id, date_str)
        takes_by_medication = {}
        for take in takes:
            med_id = take["medicationId"]
            if med_id not in takes_by_medication:
                takes_by_medication[med_id] = []
            takes_by_medication[med_id].append(take)
        
        # Combine
        result = []
        for med in medications:
            med_takes = takes_by_medication.get(med["id"], [])
            # `isTakenToday` means every scheduled dose has at least one take.
            # For meds with multiple times per day this requires N takes.
            scheduled_count = max(len(med.get("times") or []), 1)
            result.append({
                "medication": med,
                "takes": med_takes,
                "isTakenToday": len(med_takes) >= scheduled_count
            })

        return result

    @staticmethod
    def _hour_in_franja(hour: int, franja: str) -> bool:
        """Map an hour (0-23) to a time-of-day franja. Mirrors the Android
        MedicationReminderCard ranges: morning 05-11, midday 12-17, night 18-04."""
        if franja == "morning":
            return 5 <= hour <= 11
        if franja == "midday":
            return 12 <= hour <= 17
        if franja == "night":
            return hour >= 18 or hour <= 4
        if franja == "all":
            return True
        return False

    async def resolve_pending_takes_for_franja(self, user_id: str, franja: str) -> List[dict]:
        """
        Return the scheduled slots (medication + HH:MM) that fall in `franja`
        and are NOT yet registered as taken today. Used by the voice-take
        confirmation flow so the patient confirms exactly what gets recorded.

        Each item: {medication_id, name, dosage, scheduled_time}.
        """
        if franja not in ("morning", "midday", "night", "all"):
            return []
        meds_with_status = await self.get_medications_with_today_status(user_id)
        pending: List[dict] = []
        for item in meds_with_status:
            med = item.get("medication") or {}
            takes = item.get("takes") or []
            taken_slots = {t.get("scheduledTime") for t in takes if t.get("scheduledTime")}
            times = [t for t in (med.get("times") or []) if t and ":" in t]
            for t in sorted(set(times)):
                try:
                    hour = int(t.split(":")[0])
                except (ValueError, IndexError):
                    continue
                if not self._hour_in_franja(hour, franja):
                    continue
                if t in taken_slots:
                    continue
                pending.append({
                    "medication_id": med.get("id"),
                    "name": med.get("name", ""),
                    "dosage": med.get("dosage", ""),
                    "scheduled_time": t,
                })
        return pending

    async def get_monthly_report(
        self,
        user_id: str,
        year: int,
        month: int
    ) -> dict:
        """Obtener reporte mensual de adherencia a medicamentos"""
        # Calcular rango de fechas
        _, days_in_month = calendar.monthrange(year, month)
        start_date = f"{year:04d}-{month:02d}-01"
        end_date = f"{year:04d}-{month:02d}-{days_in_month:02d}"
        
        # Obtener medicamentos activos
        medications = await self.get_medications(user_id, include_inactive=True)
        
        # Obtener todas las tomas del mes
        cursor = self.medication_takes.find({
            "userId": user_id,
            "date": {"$gte": start_date, "$lte": end_date}
        })
        
        takes = []
        async for doc in cursor:
            takes.append(MedicationTakeDB.to_response(doc))
        
        # Agrupar tomas por medicamento y fecha
        takes_by_med = {}
        for take in takes:
            med_id = take["medicationId"]
            if med_id not in takes_by_med:
                takes_by_med[med_id] = {}
            
            date_str = take["date"]
            if date_str not in takes_by_med[med_id]:
                takes_by_med[med_id][date_str] = 0
            takes_by_med[med_id][date_str] += 1
        
        # Calcular estadísticas por medicamento
        medication_stats = []
        total_adherence = 0
        
        for med in medications:
            daily_takes = takes_by_med.get(med["id"], {})
            days_taken = len(daily_takes)
            adherence = (days_taken / days_in_month) * 100 if days_in_month > 0 else 0
            total_adherence += adherence
            
            medication_stats.append({
                "medicationId": med["id"],
                "medicationName": med["name"],
                "totalDays": days_in_month,
                "daysTaken": days_taken,
                "adherencePercentage": round(adherence, 1),
                "dailyTakes": daily_takes
            })
        
        # Nombres de meses en español
        month_names = [
            "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
        ]
        
        overall_adherence = total_adherence / len(medications) if medications else 0
        
        return {
            "userId": user_id,
            "month": f"{year:04d}-{month:02d}",
            "year": year,
            "monthName": month_names[month],
            "medications": medication_stats,
            "overallAdherence": round(overall_adherence, 1)
        }
    
    async def get_calendar_events(
        self,
        user_id: str,
        year: int,
        month: int
    ) -> List[dict]:
        """Obtener eventos del calendario para un mes"""
        _, days_in_month = calendar.monthrange(year, month)
        
        # Get medications count
        medications = await self.get_medications(user_id)
        total_medications = len(medications)
        
        # Get all takes for the month
        start_date = f"{year:04d}-{month:02d}-01"
        end_date = f"{year:04d}-{month:02d}-{days_in_month:02d}"
        
        cursor = self.medication_takes.find({
            "userId": user_id,
            "date": {"$gte": start_date, "$lte": end_date}
        })
        
        takes_by_date = {}
        async for doc in cursor:
            date_str = doc["date"]
            if date_str not in takes_by_date:
                takes_by_date[date_str] = set()
            takes_by_date[date_str].add(doc["medicationId"])
        
        # Generate event list
        events = []
        for day in range(1, days_in_month + 1):
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            medications_taken = len(takes_by_date.get(date_str, set()))
            
            events.append({
                "date": date_str,
                "hasMedication": total_medications > 0,
                "medicationsTaken": medications_taken,
                "totalMedications": total_medications
            })
        
        return events
