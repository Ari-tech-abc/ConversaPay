"""
Configuration settings for ConversaPay Site Builder.
Loads environment variables and provides application settings.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    APP_NAME: str = "ConversaPay Site Builder"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # API Keys
    GEMINI_API_KEY: Optional[str] = None
    
    # CORS
    CORS_ORIGINS: list = [
        "https://conversapay.org",
        "https://www.conversapay.org",
        "https://app.conversapay.org",
        "https://builder.conversapay.org",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ]
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    RELOAD: bool = True
    
    # Logging
    LOG_LEVEL: str = "info"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()