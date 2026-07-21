"""
Configuration management for ConversaPay backend.
Loads environment variables and provides centralized configuration.
"""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow"
    )

    # Application
    # FIX C6: DEBUG must default to False so production is safe even if .env omits the key.
    SECRET_KEY: str
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    
    def __init__(self, **data):
        super().__init__(**data)
        # FIX C6: Validate DEBUG is False in production
        if self.is_production and self.DEBUG:
            raise ValueError("DEBUG must be False in production environment")
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY is required")
        if not self.SUPABASE_URL or not self.SUPABASE_ANON_KEY:
            raise ValueError("Supabase credentials are required")

    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # AI
    GEMINI_API_KEY: str

    # Stripe (Optional - being replaced by PayMe)
    STRIPE_API_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRO_PLAN_PRICE_ID: Optional[str] = None

    # PayMe (Israeli Payment Gateway)
    PAYME_PAY_KEY: str
    PAYME_SELLER_KEY: str
    PAYME_SELLER_ID: str
    PAYME_BUSINESS_ID: str
    PAYME_API_URL: str = "https://live.payme.io/api"
    PAYME_SANDBOX_URL: str = "https://sandbox.payme.io/api"

    # Email (Resend)
    RESEND_API_KEY: str
    EMAIL_FROM_ADDRESS: str
    EMAIL_FROM_NAME: str = "ConversaPay"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000"

    # URLs
    FRONTEND_URL: str = "http://localhost:8000"
    BACKEND_URL: str = "http://localhost:8000"
    BASE_URL: str = "http://localhost:8000"

    # Monitoring (Optional)
    SENTRY_DSN: Optional[str] = None
    UPTIMEROBOT_API_KEY: Optional[str] = None

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT.lower() == "development"


# Global settings instance
settings = Settings()
