"""Repair missed subscription confirmations. This worker never creates a charge."""
from __future__ import annotations
from datetime import datetime, timezone

from backend.services.subscription_catalog import subscription_plan, invoice_confirms_subscription
from backend.services.subscription_checkout import billing_rpc
from backend.services.subscription_gateway import get_subscription_gateway


def reconcile_attempt(db, attempt: dict, gateway=None) -> str:
    session_id = attempt.get("provider_session_id")
    if not session_id:
        return "needs_review"  # Do not retry an unknown external operation as a new charge.
    gateway = gateway or get_subscription_gateway(attempt["provider"])
    gateway.ensure_ready()
    session = gateway.retrieve_checkout(session_id)
    metadata = session.get("metadata") or {}
    if session.get("id") != session_id or session.get("mode") != "subscription" or metadata.get("user_id") != attempt["user_id"] or metadata.get("checkout_attempt_id") != attempt["id"]:
        raise ValueError("billing_session_mismatch")
    if session.get("status") == "expired":
        result = billing_rpc(db, "finish_subscription_checkout", {"p_id": attempt["id"], "p_user_id": attempt["user_id"], "p_session_id": session_id, "p_url": None, "p_status": "expired"})
        if result.get("error"):
            raise ValueError(result["error"])
        return "expired"
    if session.get("status") != "complete" or session.get("payment_status") != "paid":
        return "pending"
    plan = subscription_plan(attempt["plan_type"])
    if session.get("amount_total") != plan.amount_minor or str(session.get("currency") or "").upper() != plan.currency:
        raise ValueError("billing_payment_mismatch")
    subscription_id = session.get("subscription")
    subscription_id = subscription_id.get("id") if isinstance(subscription_id, dict) else subscription_id
    if not subscription_id:
        raise ValueError("billing_subscription_missing")
    subscription = gateway.retrieve_subscription(subscription_id)
    identity = subscription.get("metadata") or {}
    if subscription.get("id") != subscription_id or identity.get("user_id") != attempt["user_id"] or identity.get("checkout_attempt_id") != attempt["id"] or identity.get("plan_type") != plan.key:
        raise ValueError("billing_subscription_mismatch")
    if not invoice_confirms_subscription(subscription, plan):
        return "pending"
    # Imported here to keep the durable checkout service independent of persistence.
    from backend.services.subscription_service import apply_subscription_state, period_end_iso, subscription_period_end
    applied = apply_subscription_state(user_id=attempt["user_id"], plan_type=plan.key,
        subscription_status=subscription.get("status"), subscription_expires_at=period_end_iso(subscription_period_end(subscription)),
        stripe_subscription_id=subscription_id, customer_id=subscription.get("customer"),
        cancel_at_period_end=bool(subscription.get("cancel_at_period_end")), stripe_subscription=subscription, payment_confirmed=True, db=db)
    return "confirmed" if applied else "conflict"


def reconcile_cancellation(db, row: dict, gateway=None) -> str:
    gateway = gateway or get_subscription_gateway(row["provider"])
    gateway.ensure_ready()
    snapshot = gateway.retrieve_subscription(row["provider_subscription_id"])
    if snapshot.get("id") != row["provider_subscription_id"]:
        raise ValueError("billing_subscription_mismatch")
    if not (snapshot.get("cancel_at_period_end") is True or snapshot.get("status") == "canceled"):
        return "pending"
    result = billing_rpc(db, "confirm_subscription_cancellation", {
        "p_id": row["id"], "p_user_id": row["user_id"], "p_subscription_id": row["provider_subscription_id"],
    })
    if result.get("error"):
        raise ValueError(result["error"])
    return "confirmed"


def reconcile_pending(db, limit: int = 25, apply: bool = False) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    report = {"examined": 0, "applied": apply, "outcomes": {}, "needs_review": []}
    for table, states, reconcile in [
        ("subscription_checkout_attempts", ["creating", "open"], reconcile_attempt),
        ("subscription_cancellations", ["requested"], reconcile_cancellation),
    ]:
        rows = db.table(table).select("*").in_("status", states).order("updated_at").order("id").limit(limit).execute().data or []
        report["examined"] += len(rows)
        for row in rows:
            outcome = "ready_to_check"
            if not apply and table == "subscription_checkout_attempts" and not row.get("provider_session_id"):
                outcome = "needs_review"
            if apply:
                try:
                    outcome = reconcile(db, row)
                except Exception:
                    outcome = "retry_later"
                # Rotate pending failures, so old ambiguous operations cannot starve
                # other users' confirmations in the next bounded worker run.
                db.table(table).update({"updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", row["id"]).in_("status", states).execute()
            key = table + ":" + outcome
            report["outcomes"][key] = report["outcomes"].get(key, 0) + 1
            if outcome in {"needs_review", "conflict"}:
                report["needs_review"].append(row["id"])
    return report
