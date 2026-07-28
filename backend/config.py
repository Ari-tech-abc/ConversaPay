"""Configuration management for ConversaPay backend."""
from typing import List, Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="allow")
    SECRET_KEY: str
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    GEMINI_API_KEY: str
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRO_PRICE_ID: Optional[str] = None
    STRIPE_PREMIUM_PRICE_ID: Optional[str] = None
    STRIPE_SUCCESS_URL: Optional[str] = None
    STRIPE_CANCEL_URL: Optional[str] = None
    RESEND_API_KEY: str
    EMAIL_FROM_ADDRESS: str
    EMAIL_FROM_NAME: str = "ConversaPay"
    ADMIN_SECRET_PATH: str = ""
    WEBHOOK_VERIFY_TOKEN: Optional[str] = None
    WEBHOOK_SIGNING_SECRET: Optional[str] = None
    CORS_ORIGINS: str = "https://conversapay.org"
    FRONTEND_URL: str = "https://conversapay.org"
    BACKEND_URL: str = "https://conversapay.org"
    BASE_URL: str = "https://conversapay.org"
    SENTRY_DSN: Optional[str] = None
    UPTIMEROBOT_API_KEY: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.is_production and self.DEBUG:
            raise ValueError("DEBUG must be False in production environment")
        if not self.SECRET_KEY or not self.SUPABASE_URL or not self.SUPABASE_ANON_KEY:
            raise ValueError("SECRET_KEY and Supabase credentials are required")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip().rstrip("/") for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"


settings = Settings()
