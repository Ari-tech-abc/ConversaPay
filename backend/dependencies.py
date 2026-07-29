"""FastAPI dependency providers for request-scoped Supabase clients."""
from __future__ import annotations
from collections.abc import Generator
from supabase import Client, create_client
from backend.config import settings

def get_supabase() -> Generator[Client, None, None]:
    """Provide a request-scoped synchronous Supabase client."""
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    try:
        yield client
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

def get_supabase_service() -> Generator[Client, None, None]:
    """Provide a request-scoped service-role Supabase client."""
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    try:
        yield client
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
