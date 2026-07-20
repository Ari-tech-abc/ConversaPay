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


# Plan pricing in Israeli Shekels (₪)
PLAN_PRICES = {
    "pro": 200,      # ₪200/month
    "premium": 350,  # ₪350/month
}


class PayMeService:
    """
    Service wrapper for PayMe API interactions.
    Uses PayMe's Hosted Payment Page and Tokenization for recurring charges.
    """
    
    def __init__(self):
        # Use verified live PayMe endpoint
        self.api_url = "https://live.payme.io/api"
        self.seller_payme_id = settings.PAYME_SELLER_ID
        logger.info(f"PayMe Service initialized with API URL: {self.api_url}")
    
    async def create_hosted_setup_session(
        self,
        user_id: str,
        plan_type: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a PayMe hosted payment page session for subscription.
        
        Args:
            user_id: The user's unique identifier (for tenant identification)
            plan_type: Either "pro" (200 ₪) or "premium" (350 ₪)
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect after cancelled payment
        
        Returns:
            Dictionary containing sale_url and other payment details
        """
        # Validate plan type
        if plan_type not in PLAN_PRICES:
            raise ValueError(f"Invalid plan type: {plan_type}. Must be 'pro' or 'premium'")
        
        # Get price in agorot (NIS * 100)
        amount_nis = PLAN_PRICES[plan_type]
        amount_agorot = amount_nis * 100
        
        # Build payload for PayMe API according to live.payme.io specs
        payload = {
            "seller_payme_id": self.seller_payme_id,
            "sale_price": amount_agorot,
            "currency": "ILS",
            "product_name": f"ConversaPay {plan_type.capitalize()} Plan",
            "language": "he",
            "sale_return_url": "https://www.conversapay.org/dashboard.html?payment=success",
            
            # Subscription parameters for recurring billing (הוראת קבע)
            "sub_create": "1",
            "sub_price": amount_agorot,
            "sub_period": "1",
            "sub_interval": "months",
            "sub_iteration_type": "1"
        }
        
        try:
            # Construct the full URL
            full_url = f"{self.api_url}/generate-sale"
            logger.info(f"Making PayMe API request to: {full_url}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    full_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"PayMe sale created for user {user_id}, plan: {plan_type}")
                
                return {
                    "sale_url": data.get("sale_url"),
                    "payme_sale_id": data.get("payme_sale_id"),
                    "amount_nis": amount_nis,
                    "plan_type": plan_type,
                }
                
        except httpx.HTTPError as e:
            logger.error(f"PayMe API error: {str(e)}")
            raise Exception(f"Failed to create PayMe payment session: {str(e)}")
    
    async def verify_webhook_signature(
        self,
        payload: Dict[str, Any],
        signature: Optional[str] = None
    ) -> bool:
        """
        Verify the webhook signature from PayMe.
        In production, implement proper signature verification.
        """
        # For now, basic validation - in production, verify HMAC signature
        if not payload:
            return False
        
        # Check required fields exist
        required_fields = ["sale_id", "status", "amount"]
        return all(field in payload for field in required_fields)
    
    def get_plan_price(self, plan_type: str) -> int:
        """Get the plan price in Agora (NIS * 100)."""
        if plan_type not in PLAN_PRICES:
            raise ValueError(f"Invalid plan type: {plan_type}")
        return PLAN_PRICES[plan_type] * 100


# Global service instance
payme_service = PayMeService()