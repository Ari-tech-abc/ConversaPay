"""Recover durable merchant checkouts and missed webhooks without charging cards."""
import asyncio
import logging
from datetime import datetime,timedelta,timezone
from backend.services.reconciliation_service import reconcile_orders

logger=logging.getLogger(__name__)

async def run_once(db):
    now=datetime.now(timezone.utc)
    payments=await asyncio.to_thread(lambda:db.table("payments").select("id,business_id,metadata").in_("status",["pending","processing"]).lt("created_at",(now-timedelta(minutes=2)).isoformat()).order("reconciliation_checked_at",nullsfirst=True).limit(25).execute())
    for payment in payments.data or []:
        await asyncio.to_thread(lambda:db.table("payments").update({"reconciliation_checked_at":now.isoformat()}).eq("id",payment["id"]).execute())
        if (payment.get("metadata") or {}).get("provider")!="stripe":continue
        try:await asyncio.to_thread(reconcile_orders,payment["business_id"],0,1,payment["id"])
        except Exception:logger.warning("Merchant payment reconciliation pending: %s",payment["id"])
    orders=await asyncio.to_thread(lambda:db.table("orders").select("*,payments(id)").eq("status","pending").not_.is_("stripe_account_id","null").lt("created_at",(now-timedelta(minutes=2)).isoformat()).gte("created_at",(now-timedelta(hours=20)).isoformat()).order("checkout_checked_at",nullsfirst=True).limit(10).execute())
    for order in orders.data or []:
        await asyncio.to_thread(lambda:db.table("orders").update({"checkout_checked_at":now.isoformat()}).eq("id",order["id"]).execute())
        if order.get("payments"):continue
        from backend.routers.chat import _create_order_checkout
        try:
            # Reuses the original order idempotency key and merchant snapshot.
            await _create_order_checkout(order,order.get("customer_info"))
        except Exception:logger.warning("Merchant checkout recovery pending: %s",order["id"])

async def run(db):
    while True:
        try:await run_once(db)
        except asyncio.CancelledError:raise
        except Exception:logger.warning("Merchant reconciliation worker unavailable")
        await asyncio.sleep(60)
