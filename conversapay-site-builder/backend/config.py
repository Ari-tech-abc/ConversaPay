from pydantic_settings import BaseSettings
from typing import Optional
class Settings(BaseSettings):
    APP_NAME: str = "ConversaPay Site Builder"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    GEMINI_API_KEY: Optional[str] = None
    MAIN_APP_URL: str = "https://conversapay.org"
    CORS_ORIGINS: list = ["https://conversapay.org","https://www.conversapay.org","https://app.conversapay.org","https://builder.conversapay.org","http://localhost:3000","http://localhost:3001","http://localhost:8080","http://127.0.0.1:3000","http://127.0.0.1:8080"]
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    RELOAD: bool = True
    LOG_LEVEL: str = "info"
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
settings = Settings()
