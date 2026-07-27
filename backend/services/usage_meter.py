"""Small, idempotent usage-metering helper for billable events."""
from __future__ import annotations
from typing import Any


def record_usage(supabase: Any, *, business_id: str, metric: str, source: str, source_event_id: str, quantity: int = 1) -> bool:
    if quantity < 1 or not business_id or not metric or not source_event_id:
        return False
    try:
        result = supabase.table("usage_events").insert({
            "business_id": business_id,
            "metric": metric,
            "source": source,
            "source_event_id": source_event_id,
            "quantity": quantity,
        }).execute()
        return bool(result.data)
    except Exception as exc:
        if any(marker in str(exc).lower() for marker in ("duplicate", "unique", "23505", "conflict")):
            return False
        raise
