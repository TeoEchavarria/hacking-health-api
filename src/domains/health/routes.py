from fastapi import APIRouter, HTTPException, Body, Depends
from src.domains.health.schemas import SensorBatch, SensorBatchDB
from src._config.logger import get_logger
from src.core.database import get_database
from typing import Dict

logger = get_logger(__name__)

# Default user ID for unauthenticated uploads (dev/testing mode)
DEV_USER_ID = "anonymous-dev-user"

router = APIRouter(
    prefix="/health",
    tags=["health"]
)

@router.post("/sensor-data")
async def upload_sensor_data(
    batch: SensorBatch = Body(...), 
    db=Depends(get_database)
):
    """
    Upload a batch of sensor data records.
    PUBLIC ENDPOINT - No authentication required (dev/testing mode).
    MongoDB stores **one document per batch**, not per-sample.
    """
    try:
        # Extra guard, though pydantic handles min_items
        if not batch.records:
            return {"status": "success", "count": 0}

        # Use anonymous dev user since auth is disabled
        user_id = DEV_USER_ID

        logger.info(
            f"Received batch with {len(batch.records)} records from user {user_id}. "
            f"ts_range=[{batch.records[0].timestamp}..{batch.records[-1].timestamp}]"
        )
        
        # Build DB document: userId is now a fixed dev user
        db_doc = SensorBatchDB(
            userId=user_id,
            records=batch.records
        )
            
        # Insert into SINGLE sensor_batches collection
        # One document per batch
        result = await db.sensor_batches.insert_one(db_doc.model_dump())
        
        logger.info(
            f"Inserted batch document {result.inserted_id} "
            f"for user {user_id} with {len(batch.records)} records"
        )
        
        return {
            "status": "success", 
            "batchId": str(result.inserted_id),
            "count": len(batch.records)
        }
    except Exception as e:
        logger.error(f"Error processing sensor data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
