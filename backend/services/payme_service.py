"""
PayMe Payment Service
Service wrapper for interacting with the PayMe Israeli payment gateway API.
Supports 2-Tier Pricing: Pro (200 ₪/month) and Premium (350 ₪/month).
"""
import logging
from typing import Optional, Dict, Any
import httpx
from backend.config import settings

logger = logging.getLogger(__name__)

PLAN_PRICES = {
    "pro": 200,
    "premium": 350,
}


class PayMeService:
    """Service wrapper for PayMe hosted payment sessions."""

    def __init__(self):
        self.api_url = settings.PAYME_API_URL.rstrip("/")
        self.seller_payme_id = settings.PAYME_SELLER_ID
        logger.info("PayMe Service initialized")

    async def create_hosted_setup_session(
        self,
        user_id: str,
        plan_type: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a recurring hosted payment session and preserve webhook context."""
        if plan_type not in PLAN_PRICES:
            raise ValueError("Invalid plan type")

        amount_nis = PLAN_PRICES[plan_type]
        amount_agorot = amount_nis * 100
        payload = {
            "seller_payme_id": self.seller_payme_id,
            "sale_price": amount_agorot,
            "currency": "ILS",
            "product_name": f"ConversaPay {plan_type.capitalize()} Plan",
            "language": "he",
            "sale_return_url": success_url or f"{settings.FRONTEND_URL}/pay?status=success",
            "sale_cancel_url": cancel_url or f"{settings.FRONTEND_URL}/pay?status=canceled",
            # PayMe returns these fields in the IPN. They bind the confirmed
            # payment to the correct account and selected subscription tier.
            "extra1": user_id,
            "extra2": plan_type,
            "sub_create": "1",
            "sub_price": amount_agorot,
            "sub_period": "1",
            "sub_interval": "months",
            "sub_iteration_type": "1",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/generate-sale",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

            sale_url = data.get("sale_url")
            sale_id = data.get("payme_sale_id") or data.get("sale_id")
            if not sale_url or not sale_id:
                logger.error("PayMe returned an incomplete generate-sale response")
                raise ValueError("PayMe returned an incomplete payment session")

            logger.info("PayMe sale created for user %s, plan %s", user_id, plan_type)
            return {
                "sale_url": sale_url,
                "payme_sale_id": sale_id,
                "amount_nis": amount_nis,
                "plan_type": plan_type,
            }
        except httpx.HTTPError as exc:
            logger.error("PayMe API error: %s", exc)
            raise RuntimeError("Failed to create PayMe payment session") from exc

    async def verify_webhook_signature(
        self,
        payload: Dict[str, Any],
        signature: Optional[str] = None,
    ) -> bool:
        """Legacy payload validation. IPN HMAC validation lives in the webhook router."""
        if not payload:
            return False
        return all(field in payload for field in ("sale_id", "status", "amount"))

    def get_plan_price(self, plan_type: str) -> int:
        if plan_type not in PLAN_PRICES:
            raise ValueError(f"Invalid plan type: {plan_type}")
        return PLAN_PRICES[plan_type] * 100


payme_service = PayMeService()
