"""
Servicios para gestión de citas con resolución de conflictos
Usa operaciones atómicas de MongoDB para evitar colisiones (similar a Automerge)
"""
from datetime import datetime, timedelta, time as dt_time
from typing import Optional, List, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument

from src.domains.appointments.schemas import (
    AppointmentStatus,
    AppointmentResponse,
    WeekScheduleResponse
)
from src.domains.appointments.models import AppointmentSlotDB
from src._config.logger import get_logger

logger = get_logger(__name__)

class AppointmentService:
    """Servicio para gestionar citas con conflict resolution"""
    
    # Configuración de horarios
    START_HOUR = 6  # 6 AM
    END_HOUR = 18  # 6 PM
    SLOT_DURATION_MINUTES = 30
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.appointments
    
    def _generate_slot_id(self, dt: datetime) -> str:
        """Genera un ID único para el slot basado en fecha y hora"""
        return dt.strftime("%Y-%m-%d-%H-%M")
    
    def _get_slots_per_day(self) -> List[dt_time]:
        """Genera lista de horarios del día (cada 30 min entre 6am y 6pm)"""
        slots = []
        current_hour = self.START_HOUR
        current_minute = 0
        
        while current_hour < self.END_HOUR or (current_hour == self.END_HOUR and current_minute == 0):
            slots.append(dt_time(current_hour, current_minute))
            current_minute += self.SLOT_DURATION_MINUTES
            if current_minute >= 60:
                current_minute = 0
                current_hour += 1
        
        return slots
    
    def _get_week_start(self, date: Optional[datetime] = None) -> datetime:
        """Obtiene el lunes de la semana para una fecha dada"""
        if date is None:
            date = datetime.utcnow()
        
        # Asegurar que trabajamos con fecha a medianoche
        date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calcular días hasta el lunes (0 = lunes)
        days_since_monday = date.weekday()
        week_start = date - timedelta(days=days_since_monday)
        
        return week_start
    
    def _get_week_end(self, week_start: datetime) -> datetime:
        """Obtiene el domingo de la semana"""
        return week_start + timedelta(days=6)

    def _parse_date(self, date_str: str) -> datetime:
        """Parsea YYYY-MM-DD a datetime (00:00:00)."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError("Formato de fecha inválido. Use YYYY-MM-DD") from e
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    def _parse_time(self, time_str: str) -> dt_time:
        """Parsea HH:MM a datetime.time."""
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError as e:
            raise ValueError("Formato de hora inválido. Use HH:MM (24h)") from e

    def _validate_time_range(self, start_t: dt_time, end_t: dt_time) -> None:
        """Valida que el rango esté dentro del horario del sistema y sea consistente."""
        if (start_t.hour, start_t.minute) >= (end_t.hour, end_t.minute):
            raise ValueError("El rango es inválido: start_time debe ser menor que end_time")

        # Validar horario 06:00 a 18:00 (inclusive)
        if start_t.hour < self.START_HOUR or (start_t.hour == self.START_HOUR and start_t.minute < 0):
            raise ValueError("start_time debe estar dentro del horario 06:00-18:00")
        if end_t.hour > self.END_HOUR or (end_t.hour == self.END_HOUR and end_t.minute > 0):
            raise ValueError("end_time debe estar dentro del horario 06:00-18:00")

        # Validar incrementos de 30 minutos
        if start_t.minute not in (0, 30) or end_t.minute not in (0, 30):
            raise ValueError("start_time y end_time deben caer en incrementos de 30 minutos (:00 o :30)")

    async def _ensure_slots_for_date(self, date_str: str) -> None:
        """
        Asegura que existan slots para el día indicado.
        Si no existe ninguno, inicializa la semana correspondiente.
        """
        existing_count = await self.collection.count_documents({"date": date_str}, limit=1)
        if existing_count > 0:
            return
        date_dt = self._parse_date(date_str)
        week_start = self._get_week_start(date_dt)
        await self.initialize_week_slots(week_start)
    
    async def initialize_week_slots(self, week_start: Optional[datetime] = None) -> int:
        """
        Inicializa los slots para una semana completa.
        Retorna el número de slots creados.
        """
        if week_start is None:
            week_start = self._get_week_start()
        
        week_end = self._get_week_end(week_start)
        slots_created = 0
        time_slots = self._get_slots_per_day()
        
        current_date = week_start
        while current_date <= week_end:
            for time_slot in time_slots:
                # Combinar fecha y hora
                slot_datetime = datetime.combine(current_date.date(), time_slot)
                slot_id = self._generate_slot_id(slot_datetime)
                
                try:
                    doc = AppointmentSlotDB.create_document(
                        slot_id=slot_id,
                        date=current_date.strftime("%Y-%m-%d"),
                        time=time_slot.strftime("%H:%M"),
                        datetime_obj=slot_datetime
                    )
                    await self.collection.insert_one(doc)
                    slots_created += 1
                except DuplicateKeyError:
                    # Slot ya existe, continuar
                    pass
            
            current_date += timedelta(days=1)
        
        logger.info(f"Initialized {slots_created} slots for week starting {week_start.date()}")
        return slots_created
    
    async def get_week_schedule(self, week_start: Optional[datetime] = None) -> WeekScheduleResponse:
        """
        Obtiene el horario completo de una semana.
        Si la semana no tiene slots, los crea automáticamente.
        """
        if week_start is None:
            week_start = self._get_week_start()
        
        week_end = self._get_week_end(week_start)
        
        # Buscar slots existentes
        cursor = self.collection.find({
            "datetime": {
                "$gte": week_start,
                "$lte": week_end.replace(hour=23, minute=59, second=59)
            }
        }).sort("datetime", 1)
        
        existing_slots = await cursor.to_list(length=None)
        
        # Si no hay slots, inicializarlos
        if not existing_slots:
            await self.initialize_week_slots(week_start)
            # Volver a buscar
            cursor = self.collection.find({
                "datetime": {
                    "$gte": week_start,
                    "$lte": week_end.replace(hour=23, minute=59, second=59)
                }
            }).sort("datetime", 1)
            existing_slots = await cursor.to_list(length=None)
        
        slots = [AppointmentSlotDB.to_response(doc) for doc in existing_slots]
        
        return WeekScheduleResponse(
            week_start=week_start.strftime("%Y-%m-%d"),
            week_end=week_end.strftime("%Y-%m-%d"),
            slots=[AppointmentResponse(**slot) for slot in slots]
        )
    
    async def book_appointment(self, slot_id: str, name: str) -> AppointmentResponse:
        """
        Reserva una cita usando operación atómica para evitar conflictos.
        Similar a Automerge, pero usando MongoDB atomic operations.
        
        Retorna la cita actualizada o lanza excepción si no está disponible.
        """
        # Operación atómica: solo actualiza si el slot está disponible
        result = await self.collection.find_one_and_update(
            {
                "_id": slot_id,
                "status": AppointmentStatus.AVAILABLE.value
            },
            {
                "$set": {
                    "status": AppointmentStatus.BOOKED.value,
                    "booked_by": name,
                    "updated_at": datetime.utcnow()
                },
                "$inc": {
                    "version": 1  # Incrementa versión para optimistic locking
                }
            },
            return_document=True  # Retorna el documento después de actualizar
        )
        
        if result is None:
            # Verificar si el slot existe pero está ocupado
            existing = await self.collection.find_one({"_id": slot_id})
            if existing is None:
                raise ValueError(f"Slot {slot_id} no existe")
            else:
                raise ValueError(
                    f"Slot {slot_id} ya está reservado por {existing.get('booked_by')}"
                )
        
        logger.info(f"Appointment {slot_id} booked by {name}")
        return AppointmentResponse(**AppointmentSlotDB.to_response(result))

    async def book_appointment_in_range(
        self,
        date_str: str,
        start_time_str: str,
        end_time_str: str,
        name: str,
    ) -> AppointmentResponse:
        """
        Reserva una cita en un día y un rango horario, seleccionando automáticamente según disponibilidad.
        Operación atómica: elige el primer slot disponible (por datetime ascendente) y lo reserva.

        - date_str: YYYY-MM-DD
        - start_time_str / end_time_str: HH:MM (24h), en incrementos de 30 minutos

        Retorna la cita reservada (fecha/hora exacta) o lanza ValueError si no hay disponibilidad.
        """
        await self._ensure_slots_for_date(date_str)

        day_dt = self._parse_date(date_str)
        start_t = self._parse_time(start_time_str)
        end_t = self._parse_time(end_time_str)
        self._validate_time_range(start_t, end_t)

        start_dt = datetime.combine(day_dt.date(), start_t)
        end_dt = datetime.combine(day_dt.date(), end_t)

        # Operación atómica: reserva el primer slot disponible dentro del rango
        result = await self.collection.find_one_and_update(
            {
                "date": date_str,
                "status": AppointmentStatus.AVAILABLE.value,
                "datetime": {"$gte": start_dt, "$lte": end_dt},
            },
            {
                "$set": {
                    "status": AppointmentStatus.BOOKED.value,
                    "booked_by": name,
                    "updated_at": datetime.utcnow(),
                },
                "$inc": {"version": 1},
            },
            sort=[("datetime", 1)],
            return_document=ReturnDocument.AFTER,
        )

        if result is None:
            raise ValueError("No hay disponibilidad en el rango solicitado")

        booked = AppointmentResponse(**AppointmentSlotDB.to_response(result))
        logger.info(
            f"Appointment booked in range date={date_str} range=[{start_time_str}-{end_time_str}] "
            f"-> slot_id={booked.slot_id} by {name}"
        )
        return booked
    
    async def cancel_appointment(self, slot_id: str, name: str) -> AppointmentResponse:
        """
        Cancela una cita. Solo la persona que la reservó puede cancelarla.
        Usa operación atómica para evitar conflictos.
        """
        result = await self.collection.find_one_and_update(
            {
                "_id": slot_id,
                "status": AppointmentStatus.BOOKED.value,
                "booked_by": name
            },
            {
                "$set": {
                    "status": AppointmentStatus.AVAILABLE.value,
                    "booked_by": None,
                    "updated_at": datetime.utcnow()
                },
                "$inc": {
                    "version": 1
                }
            },
            return_document=True
        )
        
        if result is None:
            existing = await self.collection.find_one({"_id": slot_id})
            if existing is None:
                raise ValueError(f"Slot {slot_id} no existe")
            elif existing.get("status") != AppointmentStatus.BOOKED.value:
                raise ValueError(f"Slot {slot_id} no está reservado")
            else:
                raise ValueError(
                    f"Slot {slot_id} está reservado por otra persona. Solo {existing.get('booked_by')} puede cancelarlo."
                )
        
        logger.info(f"Appointment {slot_id} cancelled by {name}")
        return AppointmentResponse(**AppointmentSlotDB.to_response(result))
    
    async def get_appointment(self, slot_id: str) -> Optional[AppointmentResponse]:
        """Obtiene información de un slot específico"""
        doc = await self.collection.find_one({"_id": slot_id})
        if doc is None:
            return None
        return AppointmentResponse(**AppointmentSlotDB.to_response(doc))
