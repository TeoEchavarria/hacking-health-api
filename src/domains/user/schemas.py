from pydantic import BaseModel
from typing import Optional


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    name: Optional[str] = None
    created_at: str
    updated_at: str
