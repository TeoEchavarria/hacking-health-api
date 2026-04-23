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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 days
    
    # OAuth Providers
    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = None
    GITHUB_OAUTH_CLIENT_ID: Optional[str] = None
    GITHUB_OAUTH_CLIENT_SECRET: Optional[str] = None
    
    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    
    # OpenWearables Server
    OPENWEARABLES_HOST: str = "http://localhost:8000"
    OPENWEARABLES_APP_ID: Optional[str] = None
    OPENWEARABLES_APP_SECRET: Optional[str] = None
    
    # Quick Draw
    QUICKDRAW_CACHE_DIR: str = "/tmp/.quickdrawcache"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
