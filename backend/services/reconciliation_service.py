"""Reconcile pending Stripe payments using the canonical provider session key."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import create_client

from backend.config import settings
from backend.services.stripe_service import StripeServiceError, stripe_service

logger = logging.getLogger(__name__)
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


PENDING_STATUSES = {"pending", "processing"}
PAID_STATUSES = {"paid", "succeeded", "no_payment_required"}
FAILED_STATUSES = {"unpaid", "failed", "canceled"}


def _session_id_from_metadata(metadata: dict[str, Any]) -> str | None:
    """Read the canonical key and support the legacy key during migration."""
    value = metadata.get("provider_session_id") or metadata.get("session_id")
    return str(value).strip() if value else None


def _metadata_updates(session_id: str, payment_status: str, reconciled: bool = True) -> dict[str, Any]:
    return {
        "reconciled": reconciled,
        "provider": "stripe",
        "provider_session_id": session_id,
        "stripe_payment_status": payment_status,
    }


def reconcile_orders(
    business_id: str,
    older_than_minutes: int = 15,
    limit: int = 25,
) -> dict[str, Any]:
    """Reconcile old pending payments for one business.

    The database RPC remains the single write path for synchronized order/payment
    status changes. The legacy ``session_id`` metadata key is accepted only for
    backward compatibility and is not written to new records.
    """
    if older_than_minutes < 0:
        raise ValueError("older_than_minutes must be non-negative")
    if limit < 1 or limit > 250:
        raise ValueError("limit must be between 1 and 250")

    cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    ).isoformat()
    rows = (
        supabase.table("payments")
        .select(
            "id,order_id,metadata,status,orders!inner(id,status,payment_status,business_id,created_at)"
        )
        .eq("business_id", business_id)
        .in_("status", list(PENDING_STATUSES))
        .lt("created_at", cutoff)
        .limit(limit)
        .execute()
        .data
        or []
    )

    checked = updated = failed = skipped = 0

    for row in rows:
        checked += 1
        metadata = row.get("metadata") or {}
        session_id = _session_id_from_metadata(metadata)
        if not session_id:
            skipped += 1
            continue

        try:
            session = stripe_service.retrieve_checkout_session(session_id)
            payment_status = str(session.get("payment_status") or "").lower()

            if payment_status in PAID_STATUSES:
                order_status = "paid"
                payment_state = "succeeded"
                paid = True
            elif payment_status in FAILED_STATUSES:
                order_status = "pending"
                payment_state = "failed"
                paid = False
            else:
                continue

            supabase.rpc(
                "update_order_payment_atomic",
                {
                    "p_order_id": row["order_id"],
                    "p_order_status": order_status,
                    "p_payment_status": payment_state,
                    "p_metadata_updates": _metadata_updates(
                        session_id, payment_status
                    ),
                    "p_paid": paid,
                },
            ).execute()
            updated += 1
        except (StripeServiceError, ValueError, RuntimeError) as exc:
            failed += 1
            logger.warning(
                "Payment reconciliation failed payment_id=%s order_id=%s: %s",
                row.get("id"),
                row.get("order_id"),
                exc,
            )

    return {
        "business_id": business_id,
        "checked": checked,
        "updated": updated,
        "failed": failed,
        "skipped": skipped,
    }
