"""
Payments router for managing payments and Stripe integration.
Handles payment sessions, subscription checkout, and webhooks.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime
import logging
import stripe

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import (
    PaymentCreate, PaymentResponse, PaymentStatus,
    SubscriptionCreate, SubscriptionResponse,
    ProfileResponse
)
from backend.services.payment_service import payment_service

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


# ============================================
# Subscription Checkout Session
# ============================================

@router.post("/create-checkout-session", response_model=SubscriptionResponse)
async def create_subscription_checkout_session(
    request: SubscriptionCreate,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Create a Stripe Checkout session for Pro Plan subscription ($29/month).
    User must be authenticated.
    """
    try:
        # Verify the user is the owner of the request
        if request.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User ID mismatch"
            )
        
        # Build dynamic URLs based on environment
        success_url = f"{settings.FRONTEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{settings.FRONTEND_URL}/payment/canceled"
        
        # Build session parameters
        session_params = {
            'payment_method_types': ['card'],
            'mode': 'subscription',
            'success_url': success_url,
            'cancel_url': cancel_url,
            'customer_email': request.email,
            'metadata': {
                'user_id': request.user_id,
                'type': 'pro_subscription',
                'full_name': request.full_name or ''
            },
        }
        
        # Use pre-configured price ID if available, otherwise use inline price
        if settings.STRIPE_PRO_PLAN_PRICE_ID:
            session_params['line_items'] = [{
                'price': settings.STRIPE_PRO_PLAN_PRICE_ID,
                'quantity': 1,
            }]
        else:
            session_params['line_items'] = [{
                'price_data': {
                    'currency': 'ils',
                    'product_data': {
                        'name': 'מסלול PRO לעסקים',
                        'description': 'מסלול PRO - 200 ₪ לחודש',
                    },
                    'unit_amount': 20000,  # 200 ₪ in agorot (cents)
                    'recurring': {
                        'interval': 'month',
                    },
                },
                'quantity': 1,
            }]
        
        # Create Stripe checkout session for subscription
        session = stripe.checkout.Session.create(**session_params)
        
        logger.info(f"Subscription checkout session created: {session.id} for user {request.user_id}")
        
        return {
            "session_id": session.id,
            "url": session.url
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating subscription checkout session: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription checkout session"
        )


# ============================================
# Profile Management
# ============================================

@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get the current user's profile with subscription status.
    """
    try:
        result = supabase.table("profiles")\
            .select("*")\
            .eq("user_id", current_user.user_id)\
            .execute()
        
        if not result.data:
            # Create profile if it doesn't exist
            profile_data = {
                "user_id": current_user.user_id,
                "email": current_user.email,
                "is_pro": False
            }
            result = supabase.table("profiles")\
                .insert(profile_data)\
                .execute()
        
        return ProfileResponse(**result.data[0]) if result.data else None
    
    except Exception as e:
        logger.error(f"Error fetching profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch profile"
        )


# ============================================
# Order Checkout Session (existing)
# ============================================

@router.post("/checkout-session", response_model=dict)
async def create_checkout_session(
    request: dict,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Create a Stripe Checkout session for an order.
    User must be the owner of the business.
    SECURITY: Amount is fetched from database, not trusted from client request.
    """
    try:
        business_id = request.get('business_id')
        order_id = request.get('order_id')
        customer_email = request.get('customer_email')
        customer_name = request.get('customer_name')
        
        if not business_id or not order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: business_id, order_id"
            )
        
        # Verify business ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("business_id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        # Verify order exists and belongs to business
        order = supabase.table("orders")\
            .select("*")\
            .eq("id", order_id)\
            .eq("business_id", business.data[0]['id'])\
            .execute()
        
        if not order.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # SECURITY: Use amount from database, not from client request
        order_data = order.data[0]
        amount = order_data.get('total')
        currency = order_data.get('currency', 'ils')
        
        if not amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order has no total amount"
            )
        
        # Create Stripe checkout session
        success_url = f"{settings.FRONTEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{settings.FRONTEND_URL}/payment/canceled"
        
        session = await payment_service.create_checkout_session(
            business_id=business_id,
            order_id=order_id,
            amount=amount,
            currency=currency,
            customer_email=customer_email,
            customer_name=customer_name,
            success_url=success_url,
            cancel_url=cancel_url
        )
        
        # Create payment record
        payment_data = {
            "business_id": business.data[0]['id'],
            "order_id": order_id,
            "stripe_session_id": session['session_id'],
            "amount": amount,
            "currency": currency,
            "status": PaymentStatus.PENDING.value,
            "customer_email": customer_email,
            "customer_name": customer_name,
            "metadata": {"stripe_session_id": session['session_id']}
        }
        
        payment_result = supabase.table("payments")\
            .insert(payment_data)\
            .execute()
        
        logger.info(f"Checkout session created for order {order_id}")
        
        return {
            "session_id": session['session_id'],
            "url": session['url'],
            "payment_id": payment_result.data[0]['id'] if payment_result.data else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )


@router.get("/success")
async def payment_success(session_id: str):
    """
    Payment success page.
    Verifies the payment and updates order status.
    """
    try:
        # Retrieve session from Stripe
        session = await payment_service.retrieve_session(session_id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Update payment status
        payment = supabase.table("payments")\
            .select("*")\
            .eq("stripe_session_id", session_id)\
            .execute()
        
        if payment.data:
            payment_id = payment.data[0]['id']
            order_id = payment.data[0]['order_id']
            business_id = payment.data[0]['business_id']
            
            # Update payment
            supabase.table("payments")\
                .update({
                    "status": PaymentStatus.SUCCEEDED.value,
                    "paid_at": datetime.utcnow().isoformat(),
                    "metadata": {
                        **payment.data[0].get('metadata', {}),
                        "stripe_status": session['status']
                    }
                })\
                .eq("id", payment_id)\
                .execute()
            
            # Update order status
            supabase.table("orders")\
                .update({"status": "paid"})\
                .eq("id", order_id)\
                .execute()
            
            # Update customer stats
            if payment.data[0].get('customer_email'):
                customer = supabase.table("customers")\
                    .select("id")\
                    .eq("business_id", business_id)\
                    .eq("email", payment.data[0]['customer_email'])\
                    .execute()
                
                if customer.data:
                    customer_id = customer.data[0]['id']
                    amount = payment.data[0]['amount']
                    
                    supabase.table("customers")\
                        .update({
                            "total_purchases": supabase.rpc("increment", {"field": "total_purchases", "value": amount}),
                            "purchase_count": supabase.rpc("increment", {"field": "purchase_count", "value": 1}),
                            "last_purchase_at": datetime.utcnow().isoformat()
                        })\
                        .eq("id", customer_id)\
                        .execute()
            
            logger.info(f"Payment succeeded for session {session_id}")
        
        return {"status": "success", "message": "Payment completed successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing payment success: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process payment"
        )


@router.get("/canceled")
async def payment_canceled():
    """
    Payment canceled page.
    """
    return {"status": "canceled", "message": "Payment was canceled"}


# ============================================
# Stripe Webhook Handler
# ============================================

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint.
    Handles payment events and subscription events from Stripe.
    Listens for:
    - checkout.session.completed (for one-time payments)
    - invoice.payment_succeeded (for subscription payments)
    - customer.subscription.deleted (for subscription cancellations)
    """
    try:
        # Get raw body and signature
        payload = await request.body()
        signature = request.headers.get("stripe-signature")
        
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing stripe-signature header"
            )
        
        # Verify Stripe signature
        try:
            event = stripe.Webhook.construct_event(
                payload,
                signature,
                settings.STRIPE_WEBHOOK_SECRET
            )
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature"
            )
        
        # Log the event
        logger.info(f"Received Stripe webhook event: {event['type']}")
        
        # Handle checkout.session.completed event (one-time payments)
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            
            # Check if this is a subscription checkout
            metadata = session.get('metadata', {})
            if metadata.get('type') == 'pro_subscription':
                return await _handle_subscription_checkout_completed(session)
            
            # Handle regular order payment
            return await _handle_order_checkout_completed(session)
        
        # Handle invoice.payment_succeeded (subscription payments)
        elif event['type'] == 'invoice.payment_succeeded':
            invoice = event['data']['object']
            return await _handle_invoice_payment_succeeded(invoice)
        
        # Handle customer.subscription.deleted (subscription cancellation)
        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            return await _handle_subscription_deleted(subscription)
        
        # Handle other events
        logger.info(f"Unhandled event type: {event['type']}")
        return {"status": "success", "event": event['type']}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook processing failed"
        )


async def _handle_subscription_checkout_completed(session: dict) -> dict:
    """
    Handle completed subscription checkout session.
    Updates user profile with Pro status.
    """
    try:
        customer_email = session.get('customer_details', {}).get('email')
        customer_name = session.get('customer_details', {}).get('name')
        session_id = session.get('id')
        stripe_customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')
        
        logger.info(f"Processing subscription for user_id: {user_id}")
        
        if not user_id:
            logger.warning(f"No user_id in subscription session metadata: {session_id}")
            return {"status": "error", "message": "No user_id in metadata"}
        
        # Get subscription details to find expiration
        subscription_expires_at = None
        if subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(subscription_id)
                if subscription.get('current_period_end'):
                    # Convert Unix timestamp to ISO format
                    subscription_expires_at = datetime.utcfromtimestamp(
                        subscription['current_period_end']
                    ).isoformat()
            except Exception as e:
                logger.warning(f"Could not retrieve subscription details: {str(e)}")
        
        # Update or create profile
        existing_profile = supabase.table("profiles")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        
        profile_data = {
            "is_pro": True,
            "subscription_expires_at": subscription_expires_at,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": subscription_id,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if existing_profile.data:
            supabase.table("profiles")\
                .update(profile_data)\
                .eq("user_id", user_id)\
                .execute()
            logger.info(f"Updated profile for user {user_id} to Pro status")
        else:
            profile_data["user_id"] = user_id
            profile_data["email"] = customer_email
            profile_data["full_name"] = customer_name
            supabase.table("profiles")\
                .insert(profile_data)\
                .execute()
            logger.info(f"Created Pro profile for user {user_id}")
        
        return {"status": "success", "event": "subscription_checkout_completed", "processed": True}
    
    except Exception as e:
        logger.error(f"Error processing subscription checkout: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e), "event": "subscription_checkout_completed"}


async def _handle_invoice_payment_succeeded(invoice: dict) -> dict:
    """
    Handle successful subscription payment.
    Updates subscription expiration date.
    """
    try:
        subscription_id = invoice.get('subscription')
        customer_id = invoice.get('customer')
        
        logger.info(f"Processing invoice payment for subscription: {subscription_id}")
        
        if not subscription_id:
            return {"status": "error", "message": "No subscription ID in invoice"}
        
        # Get subscription to find new period end
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            current_period_end = subscription.get('current_period_end')
            
            if current_period_end:
                subscription_expires_at = datetime.utcfromtimestamp(
                    current_period_end
                ).isoformat()
                
                # Update profile with new expiration
                profile = supabase.table("profiles")\
                    .select("*")\
                    .eq("stripe_subscription_id", subscription_id)\
                    .execute()
                
                if profile.data:
                    supabase.table("profiles")\
                        .update({
                            "is_pro": True,
                            "subscription_expires_at": subscription_expires_at,
                            "updated_at": datetime.utcnow().isoformat()
                        })\
                        .eq("id", profile.data[0]['id'])\
                        .execute()
                    logger.info(f"Updated subscription expiration for profile {profile.data[0]['id']}")
        
        except Exception as e:
            logger.warning(f"Could not retrieve subscription for invoice: {str(e)}")
        
        return {"status": "success", "event": "invoice_payment_succeeded", "processed": True}
    
    except Exception as e:
        logger.error(f"Error processing invoice payment: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e), "event": "invoice_payment_succeeded"}


async def _handle_subscription_deleted(subscription: dict) -> dict:
    """
    Handle subscription deletion/cancellation.
    Revokes Pro status from user.
    """
    try:
        subscription_id = subscription.get('id')
        customer_id = subscription.get('customer')
        
        logger.info(f"Processing subscription deletion: {subscription_id}")
        
        # Update profile to revoke Pro status
        profile = supabase.table("profiles")\
            .select("*")\
            .eq("stripe_subscription_id", subscription_id)\
            .execute()
        
        if profile.data:
            supabase.table("profiles")\
                .update({
                    "is_pro": False,
                    "subscription_expires_at": None,
                    "stripe_subscription_id": None,
                    "updated_at": datetime.utcnow().isoformat()
                })\
                .eq("id", profile.data[0]['id'])\
                .execute()
            logger.info(f"Revoked Pro status for profile {profile.data[0]['id']}")
        
        return {"status": "success", "event": "subscription_deleted", "processed": True}
    
    except Exception as e:
        logger.error(f"Error processing subscription deletion: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e), "event": "subscription_deleted"}


async def _handle_order_checkout_completed(session: dict) -> dict:
    """
    Handle completed order checkout session.
    Routes to appropriate handler based on payment_flow metadata.
    
    Payment Flows:
    - 'bot_purchase': B2B flow - business owner purchasing/subscribing to a bot
    - 'chat_escrow': C2B flow - end-customer paying business through AI chatbot
    """
    try:
        # Log session data for verification
        logger.info(f"Checkout session completed: {session}")
        logger.info(f"Session ID: {session.get('id')}")
        logger.info(f"Payment status: {session.get('payment_status')}")
        
        # Extract metadata to determine payment flow
        metadata = session.get('metadata', {})
        payment_flow = metadata.get('payment_flow', 'chat_escrow')  # Default to chat_escrow
        
        logger.info(f"Routing payment flow: {payment_flow}")
        
        # Route to appropriate handler based on payment_flow
        if payment_flow == 'bot_purchase':
            return await _handle_bot_purchase_flow(session)
        elif payment_flow == 'chat_escrow':
            return await _handle_chat_escrow_flow(session)
        else:
            logger.warning(f"Unknown payment_flow: {payment_flow}, defaulting to chat_escrow")
            return await _handle_chat_escrow_flow(session)
    
    except Exception as e:
        logger.error(f"Error processing checkout.session.completed: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e), "event": "checkout.session.completed"}


async def _handle_bot_purchase_flow(session: dict) -> dict:
    """
    B2B Flow: Handle business owner purchasing/subscribing to a bot.
    
    SECURITY: Implements Double Tenant Validation Pattern to prevent cross-tenant data leaks.
    - Validates business_id and order_id against database
    - Activates bot/business status after validation
    """
    try:
        # Extract data from session
        customer_email = session.get('customer_details', {}).get('email')
        customer_name = session.get('customer_details', {}).get('name')
        session_id = session.get('id')
        payment_status = session.get('payment_status')
        amount_total = session.get('amount_total')
        currency = session.get('currency', 'ils')
        metadata = session.get('metadata', {})
        client_reference_id = session.get('client_reference_id')
        
        # Extract business_id from metadata or client_reference_id
        business_id_from_stripe = metadata.get('business_id') or client_reference_id
        order_id = metadata.get('order_id')
        
        logger.info(f"B2B Flow - Processing bot purchase for business_id: {business_id_from_stripe}, order_id: {order_id}")
        
        # ============================================
        # DOUBLE TENANT VALIDATION - CRITICAL SECURITY
        # ============================================
        if not order_id:
            logger.error("SECURITY ALERT: No order_id in Stripe session metadata for bot_purchase flow")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session: missing order_id"
            )
        
        # Step 1: Fetch the order from database by order_id
        order_result = supabase.table("orders")\
            .select("*")\
            .eq("id", order_id)\
            .execute()
        
        if not order_result.data:
            logger.error(f"SECURITY ALERT: Order not found in database for bot_purchase: {order_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        order_data = order_result.data[0]
        business_id_from_db = order_data.get('business_id')
        
        # Step 2: Validate that business_id from Stripe matches business_id in database
        if not business_id_from_db:
            logger.error(f"SECURITY ALERT: Order {order_id} has no business_id in database for bot_purchase")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid order: missing business_id"
            )
        
        if business_id_from_stripe != business_id_from_db:
            # CRITICAL SECURITY VIOLATION - Cross-tenant data leak attempt
            logger.critical(
                f"SECURITY ALERT: B2B Cross-tenant validation failed! "
                f"Stripe business_id '{business_id_from_stripe}' does not match "
                f"database business_id '{business_id_from_db}' for order {order_id}. "
                f"Possible data tampering or cross-tenant attack in bot_purchase flow."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security validation failed: business_id mismatch"
            )
        
        # Validation passed - use the business_id from database (trusted source)
        business_id = business_id_from_db
        logger.info(f"B2B Double tenant validation passed for order {order_id}, business {business_id}")
        
        # Step 3: Activate bot/business status
        business_data = {
            "subscription_tier": "pro",
            "subscription_status": "active",
            "is_active": True,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Add Stripe customer ID if available
        if session.get('customer'):
            business_data["stripe_customer_id"] = session.get('customer')
        
        # Update business to activate bot
        supabase.table("businesses")\
            .update(business_data)\
            .eq("business_id", business_id)\
            .execute()
        
        logger.info(f"B2B Bot activated for business: {business_id}")
        
        # Step 4: Find and update payment record
        if session_id:
            payment = supabase.table("payments")\
                .select("*")\
                .eq("stripe_session_id", session_id)\
                .execute()
            
            if payment.data:
                payment_id = payment.data[0]['id']
                business_uuid = payment.data[0]['business_id']
                
                # Additional validation: ensure payment record's business_id matches validated order
                if business_uuid != business_id:
                    logger.critical(
                        f"SECURITY ALERT: B2B Payment record business_id mismatch! "
                        f"Payment {payment_id} has business_id '{business_uuid}' but order {order_id} has '{business_id}'"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Security validation failed: payment business_id mismatch"
                    )
                
                # Update payment status
                supabase.table("payments")\
                    .update({
                        "status": "succeeded",
                        "paid_at": datetime.utcnow().isoformat(),
                        "metadata": {
                            **payment.data[0].get('metadata', {}),
                            "stripe_status": payment_status,
                            "stripe_session_id": session_id,
                            "amount_total": amount_total,
                            "payment_flow": "bot_purchase"
                        }
                    })\
                    .eq("id", payment_id)\
                    .execute()
                
                # Update order status
                supabase.table("orders")\
                    .update({
                        "status": "paid",
                        "updated_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", order_id)\
                    .execute()
                
                logger.info(f"B2B Order {order_id} marked as paid, bot activated")
            else:
                logger.warning(f"No payment record found for B2B session {session_id}")
        
        return {"status": "success", "event": "checkout.session.completed", "flow": "bot_purchase", "processed": True}
    
    except Exception as e:
        logger.error(f"Error processing B2B bot purchase: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e), "event": "checkout.session.completed", "flow": "bot_purchase"}


async def _handle_chat_escrow_flow(session: dict) -> dict:
    """
    C2B Flow: Handle end-customer paying business through AI Chatbot (Escrow/Direct payment).
    
    SECURITY: Validates that the escrow order belongs to the correct customer and business,
    then updates milestone status to 'funded'.
    """
    try:
        # Extract data from session
        customer_email = session.get('customer_details', {}).get('email')
        customer_name = session.get('customer_details', {}).get('name')
        session_id = session.get('id')
        payment_status = session.get('payment_status')
        amount_total = session.get('amount_total')
        currency = session.get('currency', 'ils')
        metadata = session.get('metadata', {})
        client_reference_id = session.get('client_reference_id')
        
        # Extract business_id and order_id from metadata
        business_id_from_stripe = metadata.get('business_id') or client_reference_id
        order_id = metadata.get('order_id')
        customer_id = metadata.get('customer_id')
        
        logger.info(f"C2B Flow - Processing escrow payment for business_id: {business_id_from_stripe}, order_id: {order_id}, customer_id: {customer_id}")
        
        # ============================================
        # DOUBLE TENANT VALIDATION - CRITICAL SECURITY
        # ============================================
        if not order_id:
            logger.error("SECURITY ALERT: No order_id in Stripe session metadata for chat_escrow flow")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session: missing order_id"
            )
        
        # Step 1: Fetch the order from database by order_id
        order_result = supabase.table("orders")\
            .select("*")\
            .eq("id", order_id)\
            .execute()
        
        if not order_result.data:
            logger.error(f"SECURITY ALERT: Order not found in database for chat_escrow: {order_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        order_data = order_result.data[0]
        business_id_from_db = order_data.get('business_id')
        order_customer_id = order_data.get('customer_id')
        
        # Step 2: Validate business_id
        if not business_id_from_db:
            logger.error(f"SECURITY ALERT: Order {order_id} has no business_id in database for chat_escrow")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid order: missing business_id"
            )
        
        if business_id_from_stripe != business_id_from_db:
            # CRITICAL SECURITY VIOLATION
            logger.critical(
                f"SECURITY ALERT: C2B Cross-tenant validation failed! "
                f"Stripe business_id '{business_id_from_stripe}' does not match "
                f"database business_id '{business_id_from_db}' for order {order_id}. "
                f"Possible data tampering or cross-tenant attack in chat_escrow flow."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security validation failed: business_id mismatch"
            )
        
        # Step 3: Validate customer_id if provided
        if customer_id and order_customer_id:
            if customer_id != order_customer_id:
                logger.critical(
                    f"SECURITY ALERT: C2B Customer mismatch! "
                    f"Stripe customer_id '{customer_id}' does not match "
                    f"order customer_id '{order_customer_id}' for order {order_id}."
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Security validation failed: customer_id mismatch"
                )
        
        # Validation passed - use the business_id from database (trusted source)
        business_id = business_id_from_db
        logger.info(f"C2B Double tenant validation passed for order {order_id}, business {business_id}")
        
        # Step 4: Update order status to 'paid' and mark as funded
        order_update_data = {
            "status": "paid",
            "payment_status": "funded",
            "updated_at": datetime.utcnow().isoformat()
        }
        
        supabase.table("orders")\
            .update(order_update_data)\
            .eq("id", order_id)\
            .execute()
        
        logger.info(f"C2B Order {order_id} marked as paid and funded")
        
        # Step 5: Find and update payment record
        if session_id:
            payment = supabase.table("payments")\
                .select("*")\
                .eq("stripe_session_id", session_id)\
                .execute()
            
            if payment.data:
                payment_id = payment.data[0]['id']
                business_uuid = payment.data[0]['business_id']
                
                # Additional validation: ensure payment record's business_id matches validated order
                if business_uuid != business_id:
                    logger.critical(
                        f"SECURITY ALERT: C2B Payment record business_id mismatch! "
                        f"Payment {payment_id} has business_id '{business_uuid}' but order {order_id} has '{business_id}'"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Security validation failed: payment business_id mismatch"
                    )
                
                # Update payment status
                supabase.table("payments")\
                    .update({
                        "status": "succeeded",
                        "paid_at": datetime.utcnow().isoformat(),
                        "metadata": {
                            **payment.data[0].get('metadata', {}),
                            "stripe_status": payment_status,
                            "stripe_session_id": session_id,
                            "amount_total": amount_total,
                            "payment_flow": "chat_escrow",
                            "customer_id": customer_id
                        }
                    })\
                    .eq("id", payment_id)\
                    .execute()
                
                logger.info(f"C2B Payment record updated for session {session_id}")
            else:
                logger.warning(f"No payment record found for C2B session {session_id}")
        
        # Step 6: Create or update customer record
        if customer_email and business_id:
            existing_customer = supabase.table("customers")\
                .select("*")\
                .eq("business_id", business_id)\
                .eq("email", customer_email)\
                .execute()
            
            customer_data = {
                "email": customer_email,
                "name": customer_name,
                "business_id": business_id,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Convert amount from smallest unit to main unit
            amount_in_main_unit = amount_total / 100 if amount_total else 0
            
            if existing_customer.data:
                # Update existing customer stats
                customer_id = existing_customer.data[0]['id']
                supabase.table("customers")\
                    .update({
                        "total_purchases": existing_customer.data[0].get('total_purchases', 0) + amount_in_main_unit,
                        "purchase_count": existing_customer.data[0].get('purchase_count', 0) + 1,
                        "last_purchase_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", customer_id)\
                    .execute()
            else:
                # Create new customer
                customer_data["total_purchases"] = amount_in_main_unit
                customer_data["purchase_count"] = 1
                customer_data["last_purchase_at"] = datetime.utcnow().isoformat()
                
                supabase.table("customers")\
                    .insert(customer_data)\
                    .execute()
            
            logger.info(f"C2B Customer record updated: {customer_email}")
        
        return {"status": "success", "event": "checkout.session.completed", "flow": "chat_escrow", "processed": True}
    
    except Exception as e:
        logger.error(f"Error processing C2B chat escrow: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e), "event": "checkout.session.completed", "flow": "chat_escrow"}


# ============================================
# Payment List/Detail
# ============================================

@router.get("", response_model=List[PaymentResponse])
async def get_payments(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get all payments for a business.
    User must be the owner of the business.
    """
    try:
        # Verify business ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("business_id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        business_uuid = business.data[0]['id']
        
        # Get payments
        result = supabase.table("payments")\
            .select("*")\
            .eq("business_id", business_uuid)\
            .order("created_at", desc=True)\
            .execute()
        
        return [PaymentResponse(**payment) for payment in result.data] if result.data else []
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching payments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch payments"
        )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get a specific payment by ID.
    User must be the owner of the business that owns the payment.
    """
    try:
        # Get payment
        result = supabase.table("payments")\
            .select("*")\
            .eq("id", payment_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        payment = result.data[0]
        
        # Verify ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", payment['business_id'])\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return PaymentResponse(**payment)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching payment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch payment"
        )


# ============================================
# WordPress Plugin Generator
# ============================================

@router.get("/wordpress-plugin/{business_id}")
async def get_wordpress_plugin(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Serve the static WordPress plugin file.
    User must be the owner of the business.
    """
    try:
        # Verify business ownership
        business = supabase.table("businesses")\
            .select("id, business_id, business_name")\
            .eq("business_id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        # Read the template plugin file
        from pathlib import Path
        plugin_file_path = Path(__file__).parent.parent / "templates" / "conversapay-chat.php"
        
        if not plugin_file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Plugin file not found"
            )
        
        # Read the plugin content
        plugin_content = plugin_file_path.read_text(encoding='utf-8')
        
        # Replace placeholders with actual values
        plugin_content = plugin_content.replace('{{BUSINESS_ID}}', business_id)
        plugin_content = plugin_content.replace('{{FRONTEND_URL}}', settings.FRONTEND_URL)
        
        # Return as downloadable PHP file
        from fastapi.responses import Response
        
        return Response(
            content=plugin_content.encode('utf-8'),
            media_type='application/x-httpd-php',
            headers={
                'Content-Disposition': f'attachment; filename=conversapay-chat-{business_id}.php'
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving WordPress plugin: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to serve WordPress plugin"
        )
