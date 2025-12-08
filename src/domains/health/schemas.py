from pydantic import BaseModel, Field, conlist, validator
from typing import List
from datetime import datetime

class SensorRecordInput(BaseModel):
    timestamp: int
    x: float
    y: float
    z: float

    @validator("timestamp")
    def validate_timestamp(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("timestamp must be positive")
        return v

class SensorBatch(BaseModel):
    records: conlist(SensorRecordInput, min_items=1)

class SensorBatchDB(BaseModel):
    userId: str
    records: List[SensorRecordInput]
    createdAt: datetime = Field(default_factory=datetime.utcnow)
