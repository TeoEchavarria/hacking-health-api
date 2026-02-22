from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "hacking_health"
    
    # App
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    
    # Security
    SECRET_KEY: str = "development_secret_key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # OpenAI
    OPENAI_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
