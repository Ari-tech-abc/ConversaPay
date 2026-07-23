"""Cardcom v11 webhook with server-to-server verification and idempotency."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from backend.config import settings
from backend.services.cardcom_service import CardcomError, cardcom_service
from supabase import Client, create_client

router = APIRouter(prefix="/webhooks/cardcom", tags=["cardcom-webhook"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) not in (None, ""):
            return payload[key]
    return None


def _claim(code: str) -> bool:
    try:
        supabase.table("webhook_events").insert({"provider": "cardcom", "event_id": code, "status": "received", "received_at": datetime.now(timezone.utc).isoformat()}).execute()
        return True
    except Exception as exc:
        text = str(exc).lower()
        if any(marker in text for marker in ("duplicate", "unique", "23505", "conflict", "already exists")):
            return False
        raise


@router.post("")
async def cardcom_webhook(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)

    code = str(_first(payload, "LowProfileCode", "LowProfileId", "lowProfileCode", "lowProfileId") or "").strip()
    if not code:
        raise HTTPException(400, "Missing Cardcom LowProfileCode")
    if not _claim(code):
        return {"status": "success", "processed": False, "reason": "already_processed"}

    try:
        result = await cardcom_service.verify_transaction(code)
    except (CardcomError, ValueError) as exc:
        raise HTTPException(502, "Cardcom verification failed") from exc

    if not result["verified"]:
        return {"status": "ignored", "processed": True, "reason": "transaction_not_verified"}

    return {"status": "verified", "processed": True, "transaction_id": result.get("transaction_id"), "return_value": _first(payload, "ReturnValue", "returnValue")}
