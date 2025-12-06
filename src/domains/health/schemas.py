from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class SensorRecordInput(BaseModel):
    deviceId: str
    timestamp: int
    x: float
    y: float
    z: float
    # Optional fields for metadata
    source: str = "watch"

class SensorRecordDB(SensorRecordInput):
    userId: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)

class SensorBatch(BaseModel):
    records: List[SensorRecordInput]
