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
    SECRET_KEY: str
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # AI
    GEMINI_API_KEY: str
    
    # Stripe
    STRIPE_API_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    STRIPE_PRO_PLAN_PRICE_ID: Optional[str] = None  # Optional: Use pre-configured price in Stripe

    # PayMe (Israeli Payment Gateway)
    PAYME_PAY_KEY: str
    PAYME_SELLER_KEY: str
    PAYME_API_URL: str = "https://ng.payme.co.il/api"  # Production API
    PAYME_SANDBOX_URL: str = "https://sandbox.payme.co.il/api"  # Sandbox API
    
    # Email (Resend)
    RESEND_API_KEY: str
    EMAIL_FROM_ADDRESS: str
    EMAIL_FROM_NAME: str = "ConversaPay"
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000"
    
    # URLs
    FRONTEND_URL: str = "http://localhost:8000"
    BACKEND_URL: str = "http://localhost:8000"
    BASE_URL: str = "http://localhost:8000"  # Used for generating verification links
    
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