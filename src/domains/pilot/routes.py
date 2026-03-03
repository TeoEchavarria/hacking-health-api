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
        

@router.get("/", response_model=list[PilotResponse])
async def list_pilot_registrations(
    db=Depends(get_database),
):
    """
    Lista todas las personas registradas en la prueba piloto.
    """
    try:
        cursor = db.pilot_interests.find({})
        results: list[PilotResponse] = []
        async for doc in cursor:
            results.append(
                PilotResponse(
                    id=str(doc["_id"]),
                    full_name=doc["full_name"],
                    email=doc.get("email"),
                    phone=doc.get("phone"),
                    city=doc["city"],
                    elder_age=doc["elder_age"],
                )
            )
        return results
    except Exception as e:
        logger.error(f"Error listing pilot registrations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
