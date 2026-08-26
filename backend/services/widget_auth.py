"""
Shared authorization for public-facing widget/chat endpoints.

SECURITY NOTE (read before touching this file):
Origin, Referer, and Host are client-supplied headers. Any non-browser
client (curl, requests, a server-side scraper) can set them to whatever
it wants, and browsers do NOT reliably protect Referer either (it can be
suppressed or manipulated via <meta name="referrer">, redirects, etc.).
They must NEVER be used to grant "internal" trust or bypass paywall /
API-key checks. The previous implementation trusted these headers, which
allowed anyone to bypass the PRO/PREMIUM paywall and the widget API key
requirement simply by sending `Origin: conversapay.org` (or similar).

The only three legitimate ways to treat a request as "ours" are:
  1. It targets the literal public demo business (hardcoded, no bypass
     of paywall logic involved — the demo business is meant to be open).
  2. It carries a valid, per-business widget API key.
  3. It carries a Supabase Auth bearer token belonging to the business's
     own owner (used by the dashboard's "test your widget" preview).
     Unlike Origin/Referer/Host, a bearer token is cryptographically
     verified server-side against Supabase Auth — it cannot be forged by
     a client the way a request header can, so this is a legitimate trust
     boundary. An owner previewing their own widget bypasses the plan/API
     key gate entirely (they're not "external" — it's their own business).
"""
from datetime import datetime, timezone
import hashlib
import hmac
import logging

from fastapi import HTTPException, Request

from backend.config import settings
from backend.middleware.auth import get_current_user_optional, require_business_owner_for_business_id

logger = logging.getLogger(__name__)

# The one and only business allowed to be embedded/chatted-with without
# a widget API key or a paid plan. This is a fixed literal, NOT derived
# from any request header, so it cannot be spoofed into unlocking an
# arbitrary business.
DEMO_BUSINESS_ID = "conversapay"


def _key_hash(raw_key: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def _valid_widget_key(client, business_id: str, raw_key: str | None) -> bool:
    if not raw_key:
        return False
    result = (
        client.table("api_keys")
        .select("id")
        .eq("business_id", business_id)
        .eq("key_hash", _key_hash(raw_key))
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    if not result.data:
        return False
    client.table("api_keys").update(
        {"last_used_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", result.data["id"]).execute()
    return True


async def _is_authenticated_owner(request: Request, actual_business_id: str) -> bool:
    """True only if the request carries a valid Supabase Auth bearer token
    for a user who owns `actual_business_id`. Never raises — a missing or
    invalid token just means this path doesn't apply, so the caller falls
    through to the demo/API-key checks."""
    user = await get_current_user_optional(request)
    if not user:
        return False
    try:
        require_business_owner_for_business_id(actual_business_id, user)
        return True
    except HTTPException:
        return False


async def authorize_widget_request(
    *,
    requested_business_id: str,
    actual_business_id: str,
    plan_type: str,
    request: Request,
    client,
) -> None:
    """Raise HTTPException if this public request isn't allowed through.

    `requested_business_id` is whatever the caller passed in the URL/body
    (could be the friendly slug or the UUID). `actual_business_id` is the
    resolved DB id used for the api_keys lookup.

    Does NOT consult Origin/Referer/Host for anything security-relevant.
    """
    if requested_business_id == DEMO_BUSINESS_ID or actual_business_id == DEMO_BUSINESS_ID:
        return

    if await _is_authenticated_owner(request, actual_business_id):
        return

    if plan_type == "free":
        raise HTTPException(403, "External widget access requires PRO or PREMIUM")

    if not _valid_widget_key(client, actual_business_id, request.headers.get("X-Widget-Key")):
        raise HTTPException(401, "Valid widget API key required")