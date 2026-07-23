"""Cardcom v11 webhook with server verification and idempotent settlement."""
from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from supabase import Client, create_client

from backend.config import settings
from backend.services.cardcom_service import CardcomError, cardcom_service

router = APIRouter(prefix="/webhooks/cardcom", tags=["cardcom-webhook"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) not in (None, ""):
            return payload[key]
    return None


def _next_month(value: datetime) -> str:
    month = value.month + 1
    year = value.year + (1 if month == 13 else 0)
    month = 1 if month == 13 else month
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day).isoformat()


def _claim(code: str) -> bool:
    try:
        supabase.table("webhook_events").insert({"provider": "cardcom", "event_id": code, "status": "verified", "received_at": datetime.now(timezone.utc).isoformat()}).execute()
        return True
    except Exception as exc:
        text = str(exc).lower()
        if any(marker in text for marker in ("duplicate", "unique", "23505", "conflict", "already exists")):
            return False
        raise


def _settle_return_value(return_value: str | None, transaction: dict[str, Any]) -> None:
    if not return_value:
        return
    parts = return_value.split(":")
    if len(parts) == 3 and parts[0] == "subscription":
        user_id, plan = parts[1], parts[2]
        if plan not in {"pro", "premium"}:
            raise HTTPException(400, "Unsupported subscription plan")
        now = datetime.now(timezone.utc)
        supabase.table("profiles").update({"plan_type": plan, "subscription_expires_at": _next_month(now), "updated_at": now.isoformat()}).eq("user_id", user_id).execute()
        return

    order_id = return_value
    order = supabase.table("orders").select("id,total,currency,payment_status").eq("id", order_id).maybe_single().execute()
    if not order.data:
        raise HTTPException(404, "Order not found")
    expected_amount = round(float(order.data.get("total") or 0), 2)
    received_amount = transaction.get("amount")
    if received_amount is not None and float(received_amount) > 0:
        normalized = float(received_amount) / 100 if float(received_amount) > expected_amount * 2 else float(received_amount)
        if round(normalized, 2) != expected_amount:
            raise HTTPException(400, "Cardcom amount does not match order")
    received_currency = transaction.get("currency")
    if received_currency and str(received_currency).upper() != str(order.data.get("currency", "ILS")).upper():
        raise HTTPException(400, "Cardcom currency does not match order")
    if order.data.get("payment_status") != "paid":
        supabase.table("orders").update({"status": "paid", "payment_status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", order_id).execute()
        supabase.table("payments").update({"status": "succeeded", "paid_at": datetime.now(timezone.utc).isoformat(), "metadata": {"provider": "cardcom", "transaction_id": transaction.get("transaction_id")}}).eq("order_id", order_id).eq("status", "pending").execute()


@router.post("")
async def cardcom_webhook(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        payload = dict(await request.form())

    code = str(_first(payload, "LowProfileCode", "LowProfileId", "lowProfileCode", "lowProfileId") or "").strip()
    if not code:
        raise HTTPException(400, "Missing Cardcom LowProfileCode")

    try:
        transaction = await cardcom_service.verify_transaction(code)
    except (CardcomError, ValueError) as exc:
        raise HTTPException(502, "Cardcom verification failed") from exc
    if not transaction["verified"]:
        return {"status": "ignored", "processed": False, "reason": "transaction_not_verified"}
    if not _claim(code):
        return {"status": "success", "processed": False, "reason": "already_processed"}

    _settle_return_value(str(_first(payload, "ReturnValue", "returnValue") or "") or None, transaction)
    return {"status": "verified", "processed": True, "transaction_id": transaction.get("transaction_id")}
