from pydantic import BaseModel, Field, validator
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
    records: List[SensorRecordInput] = Field(min_length=1)

class SensorBatchDB(BaseModel):
    userId: str
    records: List[SensorRecordInput]
    createdAt: datetime = Field(default_factory=datetime.utcnow)
