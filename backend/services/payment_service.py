"""
Stripe payment service for ConversaPay.
Handles payment sessions, webhooks, and order status updates.
"""
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime
import stripe

from backend.config import settings
from backend.models.schemas import PaymentStatus, OrderStatus

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.STRIPE_API_KEY


class PaymentService:
    """Service for handling Stripe payments."""
    
    @staticmethod
    async def create_checkout_session(
        business_id: str,
        order_id: str,
        amount: float,
        currency: str = "ils",
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout session.
        
        Args:
            business_id: Business identifier
            order_id: Order identifier
            amount: Amount in the smallest currency unit (e.g., agorot for ILS)
            currency: Currency code (default: ils)
            customer_email: Customer email
            customer_name: Customer name
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect after canceled payment
            metadata: Additional metadata to store with the session
            
        Returns:
            Dict with session details including URL
        """
        try:
            # Convert amount to smallest currency unit (e.g., agorot for ILS)
            # Stripe expects amounts in the smallest unit (cents, agorot, etc.)
            amount_in_smallest_unit = int(amount * 100)
            
            # Build URLs
            if not success_url:
                # Redirect to frontend pay.html with session_id
                success_url = f"{settings.FRONTEND_URL}/pay.html?session_id={{CHECKOUT_SESSION_ID}}"
            if not cancel_url:
                cancel_url = f"{settings.FRONTEND_URL}/pay.html"
            
            # Create line items
            line_items = [{
                'price_data': {
                    'currency': currency,
                    'product_data': {
                        'name': f'Order #{order_id}',
                    },
                    'unit_amount': amount_in_smallest_unit,
                },
                'quantity': 1,
            }]
            
            # Create checkout session
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=customer_email,
                metadata={
                    'business_id': business_id,
                    'order_id': order_id,
                    'customer_name': customer_name or '',
                    **(metadata or {})
                }
            )
            
            logger.info(f"Stripe checkout session created: {session.id} for order {order_id}")
            
            return {
                'session_id': session.id,
                'url': session.url,
                'status': 'created'
            }
        
        except Exception as e:
            logger.error(f"Error creating Stripe checkout session: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    async def retrieve_session(session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a Stripe Checkout session.
        
        Args:
            session_id: Stripe session ID
            
        Returns:
            Session details or None if not found
        """
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            return {
                'id': session.id,
                'status': session.status,
                'payment_status': session.payment_status,
                'amount_total': session.amount_total / 100,  # Convert back to main unit
                'customer_email': session.customer_details.email if session.customer_details else None,
                'metadata': session.metadata
            }
        except Exception as e:
            logger.error(f"Error retrieving Stripe session: {str(e)}")
            return None
    
    @staticmethod
    async def handle_webhook(payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Handle Stripe webhook events.
        
        Args:
            payload: Raw webhook payload
            signature: Stripe signature header
            
        Returns:
            Dict with event data and processed status
        """
        try:
            # Verify webhook signature
            event = stripe.Webhook.construct_event(
                payload,
                signature,
                settings.STRIPE_WEBHOOK_SECRET
            )
            
            event_type = event['type']
            event_data = event['data']['object']
            
            logger.info(f"Received Stripe webhook: {event_type}")
            
            # Process different event types
            if event_type == 'checkout.session.completed':
                return await PaymentService._handle_checkout_completed(event_data)
            
            elif event_type == 'checkout.session.async_payment_succeeded':
                return await PaymentService._handle_payment_succeeded(event_data)
            
            elif event_type == 'checkout.session.async_payment_failed':
                return await PaymentService._handle_payment_failed(event_data)
            
            elif event_type == 'checkout.session.expired':
                return await PaymentService._handle_session_expired(event_data)
            
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")
                return {'status': 'unhandled', 'event_type': event_type}
        
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    async def _handle_checkout_completed(session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle checkout.session.completed event."""
        metadata = session_data.get('metadata', {})
        business_id = metadata.get('business_id')
        order_id = metadata.get('order_id')
        
        logger.info(f"Checkout completed for business {business_id}, order {order_id}")
        
        # This will be handled by the webhook endpoint in the router
        # which will update the database accordingly
        return {
            'status': 'processed',
            'event': 'checkout_completed',
            'business_id': business_id,
            'order_id': order_id,
            'session_id': session_data.get('id')
        }
    
    @staticmethod
    async def _handle_payment_succeeded(session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle successful payment."""
        metadata = session_data.get('metadata', {})
        business_id = metadata.get('business_id')
        order_id = metadata.get('order_id')
        
        logger.info(f"Payment succeeded for business {business_id}, order {order_id}")
        
        return {
            'status': 'processed',
            'event': 'payment_succeeded',
            'business_id': business_id,
            'order_id': order_id
        }
    
    @staticmethod
    async def _handle_payment_failed(session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle failed payment."""
        metadata = session_data.get('metadata', {})
        business_id = metadata.get('business_id')
        order_id = metadata.get('order_id')
        
        logger.warning(f"Payment failed for business {business_id}, order {order_id}")
        
        return {
            'status': 'processed',
            'event': 'payment_failed',
            'business_id': business_id,
            'order_id': order_id
        }
    
    @staticmethod
    async def _handle_session_expired(session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle expired session."""
        metadata = session_data.get('metadata', {})
        business_id = metadata.get('business_id')
        order_id = metadata.get('order_id')
        
        logger.warning(f"Session expired for business {business_id}, order {order_id}")
        
        return {
            'status': 'processed',
            'event': 'session_expired',
            'business_id': business_id,
            'order_id': order_id
        }
    
    @staticmethod
    async def create_payment_intent(
        business_id: str,
        amount: float,
        currency: str = "ils",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a Stripe Payment Intent.
        Useful for custom payment flows.
        
        Args:
            business_id: Business identifier
            amount: Amount in main currency unit
            currency: Currency code
            metadata: Additional metadata
            
        Returns:
            Dict with payment intent details
        """
        try:
            amount_in_smallest_unit = int(amount * 100)
            
            intent = stripe.PaymentIntent.create(
                amount=amount_in_smallest_unit,
                currency=currency,
                metadata={
                    'business_id': business_id,
                    **(metadata or {})
                }
            )
            
            return {
                'payment_intent_id': intent.id,
                'client_secret': intent.client_secret,
                'amount': intent.amount / 100,
                'currency': intent.currency,
                'status': intent.status
            }
        
        except Exception as e:
            logger.error(f"Error creating payment intent: {str(e)}", exc_info=True)
            raise


# Import here to avoid circular dependency
from fastapi import HTTPException

# Global service instance
payment_service = PaymentService()