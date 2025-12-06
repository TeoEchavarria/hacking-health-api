from fastapi import APIRouter, HTTPException, Body, Depends
from src.domains.health.schemas import SensorBatch, SensorRecordDB
from src._config.logger import get_logger
from src.core.database import get_database
from src.domains.auth.routes import verify_token
from typing import Dict

logger = get_logger(__name__)

router = APIRouter(
    prefix="/health",
    tags=["health"]
)

@router.post("/sensor-data")
async def upload_sensor_data(
    batch: SensorBatch = Body(...), 
    user_id: str = Depends(verify_token),
    db=Depends(get_database)
):
    """
    Upload a batch of sensor data records.
    Authenticated user is enforced.
    """
    try:
        logger.info(f"Received batch of {len(batch.records)} records from user {user_id}")
        
        if not batch.records:
            return {"status": "success", "count": 0}
            
        # TODO: Validate deviceId belongs to user_id
        # For now, we trust the auth token determines the user, 
        # and we associate the deviceId in the record with this user.
        
        # Transform to DB records with userId injected
        records_dict = []
        for record in batch.records:
            # Create DB model
            db_record = SensorRecordDB(
                **record.model_dump(),
                userId=user_id
            )
            records_dict.append(db_record.model_dump())
            
        # Insert into SINGLE sensor_data collection
        result = await db.sensor_data.insert_many(records_dict)
        
        logger.info(f"Inserted {len(result.inserted_ids)} records for user {user_id}")
        
        return {"status": "success", "count": len(result.inserted_ids)}
    except Exception as e:
        logger.error(f"Error processing sensor data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
