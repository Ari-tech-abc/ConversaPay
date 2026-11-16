"""Durable subscription purchase attempts; safe across workers and retries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from backend.services.subscription_catalog import subscription_plan
from backend.services.subscription_gateway import get_subscription_gateway


class BillingConflict(RuntimeError):
    pass


class BillingStorageUnavailable(RuntimeError):
    pass


def billing_rpc(db, name: str, args: dict) -> dict[str, Any]:
    try:
        data = db.rpc(name, args).execute().data
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict) or not data:
            raise ValueError("Empty billing transaction result")
        return data
    except Exception as exc:
        raise BillingStorageUnavailable("billing_storage_unavailable") from exc


def create_subscription_checkout(db, *, user_id: str, email: str, plan_type: str) -> dict:
    plan = subscription_plan(plan_type)
    gateway = get_subscription_gateway()
    gateway.ensure_ready()
    for _ in range(2):
        attempt = billing_rpc(db, "claim_subscription_checkout", {"p_user_id": user_id, "p_provider": gateway.provider, "p_plan": plan.key})
        if attempt.get("error"):
            raise BillingConflict(attempt["error"])
        if attempt.get("plan_type") != plan.key or attempt.get("provider") != gateway.provider:
            raise BillingConflict("billing_checkout_in_progress")
        session_id = attempt.get("provider_session_id")
        if session_id:
            session = gateway.retrieve_checkout(session_id)
            if session.get("id") != session_id or session.get("mode") != "subscription" or (session.get("metadata") or {}).get("user_id") != user_id:
                raise BillingConflict("billing_session_mismatch")
            if session.get("status") == "expired":
                billing_rpc(db, "finish_subscription_checkout", {"p_id": attempt["id"], "p_user_id": user_id, "p_session_id": session_id, "p_url": None, "p_status": "expired"})
                continue
            if session.get("status") != "open":
                from backend.services.subscription_reconciliation import reconcile_attempt
                outcome = reconcile_attempt(db, attempt, gateway)
                raise BillingConflict("billing_subscription_exists" if outcome == "confirmed" else "billing_confirmation_pending")
            if session.get("amount_total") != plan.amount_minor or str(session.get("currency") or "").upper() != plan.currency:
                raise BillingConflict("billing_payment_mismatch")
            url = session.get("url")
        else:
            created = datetime.fromisoformat(attempt["created_at"].replace("Z", "+00:00"))
            # Keep well inside the provider's idempotency retention window.
            if created < datetime.now(timezone.utc) - timedelta(hours=20):
                raise BillingConflict("billing_confirmation_pending")
            session = gateway.create_checkout(plan, user_id, email, attempt["id"])
            session_id, url = session.get("session_id") or session.get("id"), session.get("url")
        parsed = urlsplit(url or "")
        if not session_id or parsed.scheme != "https" or parsed.hostname != "checkout.stripe.com" or parsed.username or parsed.password:
            raise BillingConflict("billing_invalid_checkout")
        result = billing_rpc(db, "finish_subscription_checkout", {"p_id": attempt["id"], "p_user_id": user_id, "p_session_id": session_id, "p_url": url, "p_status": "open"})
        if result.get("error"):
            raise BillingConflict(result["error"])
        return {"session_id": session_id, "url": url, "provider": gateway.provider}
    raise BillingConflict("billing_checkout_in_progress")
