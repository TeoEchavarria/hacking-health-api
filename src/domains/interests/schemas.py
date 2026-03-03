from pydantic import BaseModel, EmailStr


class InterestCreate(BaseModel):
    """Request para registrar una persona interesada en el producto solo con email."""
    email: EmailStr


class InterestResponse(BaseModel):
    """Response con el registro creado."""
    id: str
    email: EmailStr

