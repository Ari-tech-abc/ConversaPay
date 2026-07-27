"""Shared webhook security primitives.

Provider routers should verify signatures before parsing payloads and claim
provider event IDs before mutating business state.
"""
from __future__ import annotations
import hashlib
import hmac
from typing import Any


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_hmac_sha256(payload: bytes, signature: str | None, secret: str | None, *, prefix: str = "") -> bool:
    if not payload or not signature or not secret:
        return False
    supplied = signature.strip()
    if prefix and supplied.startswith(prefix):
        supplied = supplied[len(prefix):]
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def extract_event_id(payload: dict[str, Any], headers: dict[str, str] | None = None) -> str | None:
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    for key in ("x-event-id", "x-payme-event-id", "idempotency-key"):
        if headers.get(key):
            return headers[key]
    for key in ("id", "event_id", "eventId", "sale_id", "saleId", "transaction_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def claim_event(supabase: Any, *, provider: str, event_id: str, status: str | None = None) -> bool:
    """Atomically claim an event through the unique provider/event_id key."""
    if not provider or not event_id:
        return False
    try:
        supabase.table("webhook_events").insert({"provider": provider, "event_id": event_id, "status": status}).execute()
        return True
    except Exception as exc:
        message = str(exc).lower()
        if any(marker in message for marker in ("duplicate", "unique", "23505", "conflict", "already exists")):
            return False
        raise
