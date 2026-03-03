from typing import Optional

from pydantic import BaseModel, EmailStr, model_validator


class PilotCreate(BaseModel):
    """Request para registrar una persona para la prueba piloto."""

    full_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    city: str
    elder_age: int

    @model_validator(mode="after")
    def check_contact(self) -> "PilotCreate":
        """Debe proporcionar al menos correo electrónico o número de celular."""
        if not self.email and not self.phone:
            raise ValueError(
                "Debe proporcionar al menos correo electrónico o número de celular."
            )
        return self


class PilotResponse(BaseModel):
    """Response con el registro creado para la prueba piloto."""

    id: str
    full_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    city: str
    elder_age: int

