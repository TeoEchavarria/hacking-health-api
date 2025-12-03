from pydantic import BaseModel
from typing import Optional

class LoginRequest(BaseModel):
    username: str
    password: str
    fcmToken: Optional[str] = None

class RefreshRequest(BaseModel):
    refresh: str

class TokenResponse(BaseModel):
    token: str
    refresh: str
    expiry: str

class SuccessResponse(BaseModel):
    success: bool
