"""
Chat router for AI conversations.
Handles chat messages with extended context from database.
Supports AI-powered product search and order creation.
Enforces plan-based restrictions.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import Optional
import logging
from datetime import datetime

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, get_current_user_optional, require_auth
from backend.middleware.rate_limiter import check_rate_limit
from backend.models.schemas import ChatRequest, ChatResponse
from backend.services.gemini_service import gemini_service
from backend.services.session_service import session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, request_obj: Request = Depends()):
    """
    Send a message to the AI assistant.
    Public endpoint - no authentication required.
    """
    check_rate_limit(request_obj)
    
    try:
        # Get business
        business_result = supabase.table("businesses")\
            .select("*")\
            .eq("business_id", request.business_id)\
            .eq("is_active", True)\
            .execute()
        
        if not business_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        business = business_result.data[0]
        
        # Get merchant profile to check subscription tier
        owner_id = business.get('owner_id')
        profile_result = supabase.table("profiles")\
            .select("is_pro, plan_type")\
            .eq("user_id", owner_id)\
            .execute()
        
        is_pro = False
        plan_type = 'free'
        
        if profile_result.data:
            profile = profile_result.data[0]
            is_pro = profile.get('is_pro', False)
            plan_type = profile.get('plan_type', 'free')
        
        # Get or create conversation
        conversation = await session_service.get_or_create_conversation(
            business_id=business['id'],
            session_id=request.session_id or str(datetime.utcnow().timestamp()),
            channel="web"
        )
        
        conversation_id = conversation['id']
        session_id = conversation['session_id']
        
        # Get active products for this business (always loaded)
        products_result = supabase.table("products")\
            .select("*")\
            .eq("business_id", business['id'])\
            .eq("is_active", True)\
            .execute()
        
        products = products_result.data if products_result.data else []
        
        # Get customer context if provided
        customer_context = None
        if request.customer_info:
            customer = await session_service.get_or_create_customer(
                business_id=business['id'],
                email=request.customer_info.get('email'),
                phone=request.customer_info.get('phone'),
                name=request.customer_info.get('name')
            )
            
            if customer:
                orders_result = supabase.table("orders")\
                    .select("*")\
                    .eq("business_id", business['id'])\
                    .eq("customer_id", customer['id'])\
                    .order("created_at", desc=True)\
                    .limit(5)\
                    .execute()
                
                customer_context = {
                    'name': customer.get('name'),
                    'email': customer.get('email'),
                    'phone': customer.get('phone'),
                    'purchase_count': customer.get('purchase_count', 0),
                    'total_purchases': customer.get('total_purchases', 0),
                    'last_purchase_at': customer.get('last_purchase_at'),
                    'recent_orders': orders_result.data if orders_result.data else []
                }
        
        # Get conversation history
        history = await session_service.get_conversation_history(
            conversation_id=conversation_id,
            limit=20
        )
        
        conversation_history = [
            {'role': msg['role'], 'content': msg['content']}
            for msg in history
        ]
        
        # Save user message
        await session_service.add_message(
            conversation_id=conversation_id,
            role="user",
            content=request.message
        )
        
        # ============================================
        # PLAN-BASED RESTRICTION ENFORCEMENT
        # ============================================
        if not is_pro or plan_type not in ['pro', 'premium']:
            # Free users get limited AI response
            ai_response = await gemini_service.chat(
                business_id=business['id'],
                session_id=session_id,
                message=request.message,
                business_data=business,
                products=products,                    # Still pass products
                customer_context=customer_context,
                conversation_history=conversation_history
            )
            
            # Force upgrade message for free users on checkout
            if ai_response.get('intent') == 'checkout':
                ai_response['response'] = "מערכת הרכישה המלאה זמינה רק למשתמשי PRO. שדרג כדי למכור בצ'אט!"
                ai_response['intent'] = 'upgrade_required'
        else:
            # PRO/PREMIUM - Full AI access
            ai_response = await gemini_service.chat(
                business_id=business['id'],
                session_id=session_id,
                message=request.message,
                business_data=business,
                products=products,
                customer_context=customer_context,
                conversation_history=conversation_history
            )
        
        # Save assistant message
        await session_service.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=ai_response['response'],
            intent=ai_response.get('intent')
        )
        
        # Build response
        response = ChatResponse(
            intent=ai_response.get('intent', 'chat'),
            response=ai_response['response'],
            session_id=session_id,
            conversation_id=conversation_id
        )
        
        # Handle checkout for paid users
        if ai_response.get('intent') == 'checkout' and ai_response.get('action_data') and is_pro:
            action_data = ai_response['action_data']
            
            try:
                order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{datetime.utcnow().strftime('%H%M%S')}"
                
                customer_id = None
                if request.customer_info:
                    customer = await session_service.get_or_create_customer(
                        business_id=business['id'],
                        email=request.customer_info.get('email'),
                        phone=request.customer_info.get('phone'),
                        name=request.customer_info.get('name')
                    )
                    if customer:
                        customer_id = customer['id']
                
                order_data = {
                    "business_id": business['id'],
                    "customer_id": customer_id,
                    "conversation_id": conversation_id,
                    "order_number": order_number,
                    "status": "pending",
                    "payment_status": "pending",
                    "subtotal": action_data['total'],
                    "tax": 0,
                    "total": action_data['total'],
                    "currency": action_data.get('currency', 'ILS'),
                    "items": [{
                        "product_id": action_data['product_id'],
                        "item_key": action_data['item_key'],
                        "name": action_data['product_name'],
                        "quantity": action_data['quantity'],
                        "price": action_data['total'] / action_data['quantity']
                    }],
                    "customer_info": request.customer_info or {},
                    "created_at": datetime.utcnow().isoformat()
                }
                
                order_result = supabase.table("orders")\
                    .insert(order_data)\
                    .execute()
                
                if order_result.data:
                    order = order_result.data[0]
                    action_data['order_id'] = order['id']
                    action_data['order_number'] = order['order_number']
                    response.payment_url = f"/pay.html?biz={request.business_id}&order={order['id']}"
                    
            except Exception as e:
                logger.error(f"Error creating order: {str(e)}")
                action_data['error'] = str(e)
            
            response.action_data = action_data
        
        logger.info(f"Chat response for business {request.business_id}, session {session_id}")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process chat message"
        )