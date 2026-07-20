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
        self.api_url = settings.PAYME_API_URL if settings.is_production else settings.PAYME_SANDBOX_URL
        self.pay_key = settings.PAYME_PAY_KEY
        self.seller_key = settings.PAYME_SELLER_KEY
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
        
        # Get price in Agora (NIS * 100)
        amount_nis = PLAN_PRICES[plan_type]
        amount_agora = amount_nis * 100  # Convert to Agora (200 ₪ = 20000 Agora)
        
        # Build payload for PayMe API
        payload = {
            "pay_key": self.pay_key,
            "seller_key": self.seller_key,
            "amount": amount_agora,
            "currency": "ILS",
            "description": f"ConversaPay {plan_type.capitalize()} Subscription - Monthly",
            "extra1": user_id,  # Store user_id for tenant identification
            "extra2": plan_type,  # Store plan type
            "capture": True,  # Enable tokenization for recurring charges
            "generate_token": 1,  # Request card token for future billing
        }
        
        # Add optional redirect URLs
        if success_url:
            payload["success_url"] = success_url
        if cancel_url:
            payload["cancel_url"] = cancel_url
        
        try:
            # Construct the full URL and log it for debugging
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
                    "sale_id": data.get("sale_id"),
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