"""
Rutas para registro de personas interesadas en el producto.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from src.core.database import get_database
from src.domains.interests.schemas import InterestCreate, InterestResponse
from src._config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/interests",
    tags=["interests"],
)


@router.post("/", response_model=InterestResponse, status_code=201)
async def register_interest(
    body: InterestCreate,
    db=Depends(get_database),
):
    """
    Registra una persona interesada en el producto.
    Guarda nombre, email y celular (opcional) en MongoDB.
    """
    try:
        doc = {
            "name": body.name,
            "email": body.email,
            "phone": body.phone,
            "created_at": datetime.now(timezone.utc),
        }
        result = await db.interests.insert_one(doc)
        return InterestResponse(
            id=str(result.inserted_id),
            name=body.name,
            email=body.email,
            phone=body.phone,
        )
    except Exception as e:
        logger.error(f"Error registering interest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
