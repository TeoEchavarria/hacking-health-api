from pydantic import BaseModel
from typing import List
from datetime import datetime

class SensorRecord(BaseModel):
    deviceId: str
    timestamp: int
    x: float
    y: float
    z: float
    # Optional fields for metadata
    source: str = "watch"
    
class SensorBatch(BaseModel):
    records: List[SensorRecord]
