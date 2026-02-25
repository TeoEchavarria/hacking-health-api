from pydantic import BaseModel, EmailStr
from typing import Optional


class InterestCreate(BaseModel):
    """Request para registrar una persona interesada en el producto."""
    name: str
    email: EmailStr
    phone: Optional[str] = None


class InterestResponse(BaseModel):
    """Response con el registro creado."""
    id: str
    name: str
    email: EmailStr
    phone: Optional[str] = None
