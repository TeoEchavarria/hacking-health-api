from argon2 import PasswordHasher
from datetime import datetime, timedelta
from typing import Optional
from src._config.settings import settings
import secrets

ph = PasswordHasher()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return ph.verify(hashed_password, plain_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    return ph.hash(password)

def create_token() -> str:
    return secrets.token_urlsafe(32)
