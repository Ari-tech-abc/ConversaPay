"""Merchant-owned Stripe charges. Never fall back to the platform account."""
import stripe
from backend.config import settings
from backend.services.stripe_service import stripe_service


def merchant_account(db, business_id: str) -> str:
    if not settings.STRIPE_CONNECT_WEBHOOK_SECRET:
        raise ValueError("merchant_connect_webhook_required")
    rows = db.table("payment_accounts").select("stripe_account_id,status").eq("business_id", business_id).eq("provider", "stripe").neq("status", "revoked").limit(1).execute().data or []
    if not rows or not str(rows[0].get("stripe_account_id", "")).startswith("acct_"):
        raise ValueError("merchant_payment_account_required")
    stripe_service._ensure_configured()
    account = stripe.Account.retrieve(rows[0]["stripe_account_id"])
    if account.get("charges_enabled") is not True or account.get("payouts_enabled") is not True:
        raise ValueError("merchant_payment_account_not_ready")
    if rows[0]["status"]!="active":
        db.table("payment_accounts").update({"status":"active"}).eq("business_id",business_id).eq("stripe_account_id",account["id"]).execute()
    return account["id"]
