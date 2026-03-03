"""
Rutas para registro de personas interesadas en la prueba piloto.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from src._config.logger import get_logger
from src.core.database import get_database
from src.domains.pilot.schemas import PilotCreate, PilotResponse

logger = get_logger(__name__)

router = APIRouter(
    prefix="/prueba-piloto",
    tags=["prueba-piloto"],
)


@router.post("/", response_model=PilotResponse, status_code=201)
async def register_pilot(
    body: PilotCreate,
    db=Depends(get_database),
):
    """
    Registra una persona interesada en la prueba piloto.

    Solicita:
    - Nombre completo
    - Correo electrónico o número de celular (al menos uno)
    - Ciudad
    - Edad del adulto mayor
    """
    try:
        doc = {
            "full_name": body.full_name,
            "email": body.email,
            "phone": body.phone,
            "city": body.city,
            "elder_age": body.elder_age,
            "created_at": datetime.now(timezone.utc),
        }
        result = await db.pilot_interests.insert_one(doc)
        return PilotResponse(
            id=str(result.inserted_id),
            full_name=body.full_name,
            email=body.email,
            phone=body.phone,
            city=body.city,
            elder_age=body.elder_age,
        )
    except Exception as e:
        logger.error(f"Error registering pilot interest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

