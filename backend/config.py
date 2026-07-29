"""Centralized environment and filesystem configuration."""
from pathlib import Path
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
    DATABASE_URL: Optional[str] = None
    MIGRATIONS_AUTO_APPLY: bool = True
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRO_PRICE_ID: Optional[str] = None
    STRIPE_PREMIUM_PRICE_ID: Optional[str] = None
    STRIPE_SUCCESS_URL: Optional[str] = None
    STRIPE_CANCEL_URL: Optional[str] = None
    RESEND_API_KEY: str
    EMAIL_FROM_ADDRESS: str
    EMAIL_FROM_NAME: str = "Talk2Pay"
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

    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def frontend_dir(self) -> Path:
        return self.base_dir / "frontend"

    @property
    def html_dir(self) -> Path:
        return self.frontend_dir / "html"

    @property
    def images_dir(self) -> Path:
        return self.frontend_dir / "images"

    @property
    def static_dir(self) -> Path:
        return self.base_dir / "backend" / "static"

    @property
    def site_builder_dir(self) -> Path:
        return self.base_dir / "conversapay-site-builder" / "frontend"

    @property
    def migrations_dir(self) -> Path:
        return self.base_dir / "database" / "migrations"

    def ensure_delivery_directories(self) -> None:
        for directory in (self.frontend_dir, self.html_dir, self.images_dir, self.static_dir):
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
