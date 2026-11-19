"""Retryable account deletion: stop billing before deleting identity and data."""
import asyncio
import logging
import stripe
from backend.services.subscription_gateway import get_subscription_gateway
from backend.services.stripe_service import stripe_service

logger=logging.getLogger(__name__)

def delete_account_data(db,user_id):
    db.rpc("begin_account_deletion",{"p_user_id":user_id}).execute()
    rows=db.table("profiles").select("*").eq("user_id",user_id).limit(1).execute().data or []
    profile=rows[0] if rows else {}
    subscription_id=profile.get("provider_subscription_id") or profile.get("stripe_subscription_id")
    if subscription_id:
        gateway=get_subscription_gateway(profile.get("subscription_provider") or "stripe")
        subscription=gateway.retrieve_subscription(subscription_id)
        if subscription.get("status") not in {"canceled","incomplete_expired"}:
            gateway.cancel_renewal(subscription_id,"delete-account:"+user_id)
    attempts=db.table("subscription_checkout_attempts").select("provider,provider_session_id").eq("user_id",user_id).in_("status",["creating","open"]).execute().data or []
    for attempt in attempts:
        if not attempt.get("provider_session_id"):
            raise RuntimeError("Unconfirmed checkout requires billing reconciliation before deletion")
        gateway=get_subscription_gateway(attempt["provider"])
        session=gateway.retrieve_checkout(attempt["provider_session_id"])
        if session.get("status")=="open":
            stripe_service._ensure_configured()
            stripe.checkout.Session.expire(attempt["provider_session_id"])
        elif session.get("status")=="complete":
            sid=session.get("subscription")
            sid=sid.get("id") if isinstance(sid,dict) else sid
            if sid:gateway.cancel_renewal(sid,"delete-account:"+user_id)
    # Include legacy duplicate subscriptions attached to the same customer.
    if profile.get("stripe_customer_id"):
        stripe_service._ensure_configured()
        for sub in stripe.Subscription.list(customer=profile["stripe_customer_id"],status="all").auto_paging_iter():
            if sub.get("status") not in {"canceled","incomplete_expired"}:
                stripe.Subscription.modify(sub["id"],cancel_at_period_end=True,idempotency_key="delete-account:"+user_id+":"+sub["id"])
    businesses=db.table("businesses").select("id").eq("owner_id",user_id).execute().data or []
    for business in businesses:
        # A deleted store must never leave a live checkout accepting customer money.
        pending=db.table("payments").select("metadata").eq("business_id",business["id"]).in_("status",["pending","processing"]).execute().data or []
        for payment in pending:
            metadata=payment.get("metadata") or {}
            session_id=metadata.get("provider_session_id")
            if not session_id or metadata.get("provider")!="stripe":raise RuntimeError("Merchant payment requires review")
            session=stripe_service.retrieve_checkout_session(session_id,stripe_account_id=metadata.get("stripe_account_id"))
            if session.get("status")=="open":
                stripe.checkout.Session.expire(session_id,**({"stripe_account":metadata["stripe_account_id"]} if metadata.get("stripe_account_id") else {}))
        unresolved=db.table("orders").select("id,payments(id)").eq("business_id",business["id"]).eq("status","pending").not_.is_("stripe_account_id","null").execute().data or []
        if any(not order.get("payments") for order in unresolved):raise RuntimeError("Checkout recovery must complete before deletion")
    try:db.auth.admin.delete_user(user_id)
    except Exception as exc:
        if str(getattr(exc,"status",getattr(exc,"status_code","")))!="404":raise
    db.rpc("purge_account_data",{"p_user_id":user_id}).execute()

async def deletion_worker(db):
    while True:
        try:
            jobs=await asyncio.to_thread(lambda:db.table("account_deletions").select("user_id").eq("status","requested").limit(10).execute())
            for job in jobs.data or []:
                try:await asyncio.to_thread(delete_account_data,db,job["user_id"])
                except Exception:logger.warning("Account deletion pending for %s",job["user_id"])
        except asyncio.CancelledError:raise
        except Exception:logger.warning("Account deletion worker unavailable")
        await asyncio.sleep(60)
