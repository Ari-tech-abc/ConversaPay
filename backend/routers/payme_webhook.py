"""
PayMe Webhook Router
Handles Instant Payment Notifications (IPN) from PayMe payment gateway.

SECURITY FIXES:
  C2 - HMAC-SHA256 signature verification added (_verify_payme_signature).
  H5 - Idempotency check on sale_id prevents double-activation.
  M6 - payme_card_token is hashed before storage.
"""
import hashlib
import hmac as hmac_lib
from fastapi import APIRouter, HTTPException, status, Request
import logging
from datetime import datetime
from typing import Optional

from supabase import create_client, Client
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/payme", tags=["payme-webhook"])

# Single module-level client — do not recreate per request.
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


# ============================================
# Signature Verification
# ============================================

def _verify_payme_signature(raw_body: bytes, provided_sig: str) -> bool:
    """
    Verify PayMe IPN HMAC-SHA256 signature.

    PayMe signs the raw request body with PAYME_SELLER_KEY.
    The signature is sent in the 'X-Payme-Signature' HTTP header
    (adjust the header name to match your PayMe merchant panel setting).

    Returns True only when the computed digest matches the provided one.
    Uses hmac.compare_digest to prevent timing-oracle attacks.
    """
    if not provided_sig:
        return False
    secret = settings.PAYME_SELLER_KEY.encode("utf-8")
    computed = hmac_lib.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac_lib.compare_digest(computed, provided_sig.lower())


def _hash_card_token(token: str) -> str:
    """One-way SHA-256 hash of a card token for safe storage (Fix M6)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ============================================
# PayMe Webhook Endpoint
# ============================================

@router.post("", response_model=dict)
async def handle_payme_webhook(request: Request):
    """
    Handle PayMe Instant Payment Notifications (IPN).

    Security controls applied:
      1. HMAC-SHA256 signature verification (C2).
      2. sale_id idempotency — skip if already processed (H4).
      3. Card token hashed before storage (H5).
    """
    # Read raw body ONCE — needed for both signature check and JSON parse.
    raw_body = await request.body()

    # --- C2: Verify webhook authenticity before touching any data ---
    provided_sig = request.headers.get("X-Payme-Signature", "")
    if not _verify_payme_signature(raw_body, provided_sig):
        logger.warning(
            "PayMe webhook rejected: invalid or missing signature "
            f"(remote={request.client.host if request.client else 'unknown'})"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )

    try:
        import json
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    sale_id: Optional[str] = payload.get("sale_id")
    payme_status = payload.get("status")
    card_token: Optional[str] = payload.get("card_token") or payload.get("buyer_key")
    user_id: Optional[str] = payload.get("extra1")
    plan_type: Optional[str] = payload.get("extra2")

    if not sale_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing sale_id in webhook payload"
        )

    # --- H4: Idempotency — skip if this sale_id was already processed ---
    already_processed = supabase.table("profiles") \
        .select("user_id") \
        .eq("payme_sale_id", sale_id) \
        .execute()
    if already_processed.data:
        logger.info(f"PayMe webhook for sale_id={sale_id} already processed — skipping")
        return {"status": "success", "processed": False, "reason": "already_processed"}

    is_success = payme_status == "success" or str(payme_status) == "0"

    if is_success:
        await _activate_subscription(user_id, plan_type, card_token, sale_id)
    else:
        await _deactivate_subscription(user_id, sale_id)

    return {"status": "success", "processed": True}


# ============================================
# Helper Functions
# ============================================

async def _activate_subscription(
    user_id: Optional[str],
    plan_type: Optional[str],
    card_token: Optional[str],
    sale_id: str
):
    """Activate a user's subscription after successful PayMe payment."""
    if not user_id:
        logger.warning(f"No user_id in successful PayMe payment: {sale_id}")
        return

    try:
        safe_plan = plan_type if plan_type in ("pro", "premium") else "pro"

        profile_data = {
            "is_pro": True,
            "plan_type": safe_plan,
            # H5: store a one-way hash of the card token, never the raw value.
            "payme_card_token": _hash_card_token(card_token) if card_token else None,
            "payme_sale_id": sale_id,
            "subscription_activated_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        existing = supabase.table("profiles") \
            .select("user_id") \
            .eq("user_id", user_id) \
            .execute()

        if existing.data:
            supabase.table("profiles") \
                .update(profile_data) \
                .eq("user_id", user_id) \
                .execute()
        else:
            profile_data["user_id"] = user_id
            supabase.table("profiles") \
                .insert(profile_data) \
                .execute()

        logger.info(f"Activated {safe_plan} subscription for user {user_id} (sale={sale_id})")

    except Exception as e:
        logger.error(f"Failed to activate subscription: {str(e)}", exc_info=True)


async def _deactivate_subscription(user_id: Optional[str], sale_id: str):
    """Deactivate a user's subscription after failed/cancelled payment."""
    if not user_id:
        logger.warning(f"No user_id in failed PayMe payment: {sale_id}")
        return

    try:
        supabase.table("profiles") \
            .update({
                "is_pro": False,
                "plan_type": "free",
                "payme_card_token": None,
                "subscription_cancelled_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }) \
            .eq("user_id", user_id) \
            .execute()

        logger.info(f"Deactivated subscription for user {user_id} (sale={sale_id})")

    except Exception as e:
        logger.error(f"Failed to deactivate subscription: {str(e)}", exc_info=True)
