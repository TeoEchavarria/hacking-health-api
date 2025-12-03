from fastapi import APIRouter, HTTPException, Body, Depends
from src.domains.health.schemas import SensorBatch
from src._config.logger import get_logger
from src.core.database import get_database
from typing import Dict

logger = get_logger(__name__)

router = APIRouter(
    prefix="/health",
    tags=["health"]
)

@router.post("/sensor-data")
async def upload_sensor_data(batch: SensorBatch = Body(...), db=Depends(get_database)):
    """
    Upload a batch of sensor data records.
    """
    try:
        logger.info(f"Received batch of {len(batch.records)} records from device {batch.records[0].deviceId if batch.records else 'unknown'}")
        
        if not batch.records:
            return {"status": "success", "count": 0}
            
        # Insert into MongoDB
        records_dict = [r.model_dump() for r in batch.records]
        result = await db.sensor_data.insert_many(records_dict)
        
        logger.info(f"Inserted {len(result.inserted_ids)} records into MongoDB")
        
        return {"status": "success", "count": len(result.inserted_ids)}
    except Exception as e:
        logger.error(f"Error processing sensor data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
