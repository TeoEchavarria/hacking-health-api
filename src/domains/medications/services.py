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
        time: str,
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
            time=time,
            instructions=instructions,
            medication_type=medication_type
        )
        
        await self.medications.insert_one(document)
        logger.info(f"Created medication {medication_id} for user {user_id}")
        
        return MedicationDB.to_response(document)
    
    async def get_medications(self, user_id: str, include_inactive: bool = False) -> List[dict]:
        """Obtener todos los medicamentos de un usuario"""
        query = {"userId": user_id}
        if not include_inactive:
            query["isActive"] = True
        
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
        if "time" in updates:
            update_doc["$set"]["time"] = updates["time"]
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
        notes: Optional[str] = None
    ) -> Optional[dict]:
        """Registrar la toma de un medicamento"""
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
            notes=notes
        )
        
        await self.medication_takes.insert_one(document)
        logger.info(f"Recorded take {take_id} for medication {medication_id}")
        
        return MedicationTakeDB.to_response(document)
    
    async def untake_medication(
        self,
        medication_id: str,
        user_id: str,
        date_str: str
    ) -> bool:
        """Desmarcar la toma de un medicamento de un día específico"""
        # Delete the most recent take for this medication on this date
        result = await self.medication_takes.find_one_and_delete(
            {
                "medicationId": medication_id,
                "userId": user_id,
                "date": date_str
            },
            sort=[("takenAt", -1)]  # Delete the most recent one
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
            result.append({
                "medication": med,
                "takes": med_takes,
                "isTakenToday": len(med_takes) > 0
            })
        
        return result
    
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
