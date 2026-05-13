"""
Biometrics History Routes.

Handles:
- Unified biometric data queries
- Historical data retrieval with access control
- Multi-metric aggregated views

Returns empty array (not 404) for new users.
Following Single Responsibility Principle (SRP).
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from src.domains.health.schemas import BiometricsHistoryResponse
from src.domains.health.services import HealthService
from src.domains.auth.routes import verify_token_jwt
from src._config.logger import get_logger
from src.core.database import get_database

logger = get_logger(__name__)

router = APIRouter()


@router.get("/biometrics/{user_id}", response_model=BiometricsHistoryResponse)
async def get_user_biometrics(
    user_id: str,
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    days: int = Query(30, ge=1, le=90, description="Days of history"),
    auth_user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database)
):
    """
    Get biometric history for a user.

    Returns records ordered by timestamp DESC.
    Returns [] with status 200 for new users (NOT 404).

    Use this to:
    - Detect if user is new (isEmpty=true) vs has historical data
    - Get latest values for each metric type
    - Get paginated history for charts/lists
    """
    try:
        service = HealthService(db)

        # Authorization check
        has_access = await service.verify_patient_access(
            requester_id=auth_user_id,
            patient_id=user_id
        )

        if not has_access:
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para ver estos datos"
            )

        # Fetch biometric data
        result = await service.get_biometrics_history(
            user_id=user_id,
            limit=limit,
            days=days
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching biometrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
