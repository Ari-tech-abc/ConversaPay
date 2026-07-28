"""Shared HMAC verification for public webhook endpoints."""
from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from fastapi import HTTPException, Request, status

from backend.config import settings

_SIGNATURE_PREFIXES = ("sha256=", "hmac-sha256=")


def expected_hmac(secret: str, payload: bytes) -> str:
    """Return the lowercase SHA-256 HMAC for a raw request body."""
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, signature: Optional[str], secret: Optional[str]) -> bool:
    """Constant-time verification of a raw or prefixed webhook signature."""
    if not signature or not secret:
        return False

    candidate = signature.strip().lower()
    for prefix in _SIGNATURE_PREFIXES:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):]
            break

    return hmac.compare_digest(candidate, expected_hmac(secret, payload))


async def require_signed_request(request: Request, secret: Optional[str] = None) -> bytes:
    """Read and authenticate a webhook request using X-Webhook-Signature."""
    signing_secret = secret or settings.WEBHOOK_SIGNING_SECRET
    if not signing_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook signing secret is not configured",
        )

    payload = await request.body()
    signature = request.headers.get("X-Webhook-Signature")
    if not verify_signature(payload, signature, signing_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    return payload
