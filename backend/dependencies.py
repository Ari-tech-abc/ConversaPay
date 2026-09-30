"""FastAPI dependency providers for request-scoped Supabase clients."""
from __future__ import annotations
from collections.abc import Generator
from supabase import Client, ClientOptions, create_client
from backend.config import settings


def create_auth_client(*, flow_type: str = "pkce") -> Client:
    """A new user Auth client for each operation; never mutate a service client."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY,
                         options=ClientOptions(auto_refresh_token=False, persist_session=False, flow_type=flow_type))

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
