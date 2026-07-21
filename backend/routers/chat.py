"""
Chat router for AI conversations.
Handles chat messages with extended context from database.
Supports AI-powered product search and order creation.
Enforces plan-based restrictions for Free/Trial users.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer
from typing import Optional
import logging
from datetime import datetime

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, get_current_user, get_current_user_optional, require_auth
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

# Static FAQ for Free/Trial users
FREE_TIER_FAQ = [
    {
        "question": "מה זה ConversaPay?",
        "answer": "ConversaPay היא פלטפורמה המאפשרת לעסקים להוסיף צ'אטבוט AI מכירות לאתר שלהם. הבוט מנהל שיחות עם לקוחות, מציע מוצרים, ומעביר לתשלום."
    },
    {
        "question": "כיצד זה עובד?",
        "answer": "לאחר הרשמה והגדרת העסק, הווידג'ט צף מתווסף לאתר שלך. הלקוחות מתקשרים עם הבוט, והוא מנהל שיחות מכירה אוטונומיות."
    },
    {
        "question": "מהן התכונות של המסלול PRO?",
        "answer": "מסלול PRO כולל: סוכן AI מבוסס Gemini, ווידג'ט צף, סליקה מאובטחת דרך PayMe, דשבורד אנליטיקס מתקדם, והזמנות ללא הגבלה."
    },
    {
        "question": "מהן התכונות של המסלול PREMIUM?",
        "answer": "מסלול PREMIUM כולל את כל תכונות ה-PRO, ולעוסק בתוספות: נפח שיחות גבוה יותר, פריסה במספר דומיינים, תמיכה מועדפת, והכנה לאינטגרציות מתקדמות (WhatsApp, CRM)."
    },
    {
        "question": "כיצד אדפת תשלמו?",
        "answer": "אנו תומכים בכל אמצעי התשלום הגלובליים דרך PayMe, כולל כרטיסי אשראי, אפל פייס, והעברה בנקאית."
    },
    {
        "question": "האם יש חשבון ניסיון חינם?",
        "answer": "כן! אתה יכול להתחיל בחינם עם מסלול היכרות. לחץ על 'התחל בחינם' כדי ליצור חשבון."
    }
]

FREE_TIER_UPGRADE_MESSAGE = "מערכת הבינה המלאכותית ואפשרות הרכישה המהירה זמינות במסלול ה-PRO בלבד."


def _check_free_tier_faq(message: str) -> Optional[str]:
    """
    Check if the message matches any FAQ entry for free tier users.
    Returns the answer if found, None otherwise.
    """
    message_lower = message.lower().strip()
    
    for faq_item in FREE_TIER_FAQ:
        question_lower = faq_item["question"].lower()
        # Check if the message contains keywords from the question
        if any(word in message_lower for word in question_lower.split()):
            return faq_item["answer"]
    
    return None


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, request_obj: Request = Depends()):
    """
    Send a message to the AI assistant.
    Public endpoint - no authentication required.
    Includes extended context from database.
    Rate limited to 10 requests per minute per IP.
    
    Plan-based restrictions:
    - Free/Trial users: No AI access, no payments, FAQ only
    - PRO users: Full AI access, PayMe integration
    - PREMIUM users: All PRO features + advanced integrations
    """
    # Check rate limit
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
            session_id=request.session_id,
            channel="web"
        )
        
        conversation_id = conversation['id']
        session_id = conversation['session_id']
        
        # Get active products for this business
        products_result = supabase.table("products")\
            .select("*")\
            .eq("business_id", business['id'])\
            .eq("is_active", True)\
            .execute()
        
        products = products_result.data if products_result.data else []
        
        # Get customer context if provided
        customer_context = None
        if request.customer_info:
            # Try to find or create customer
            customer = await session_service.get_or_create_customer(
                business_id=business['id'],
                email=request.customer_info.get('email'),
                phone=request.customer_info.get('phone'),
                name=request.customer_info.get('name')
            )
            
            if customer:
                # Get recent orders for this customer
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
        
        # Format history for Gemini
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
        # Free/Trial users: No AI access, no payments, FAQ only
        # Support both 'pro' and 'premium' as valid paid tiers
        if not is_pro or plan_type not in ['pro', 'premium']:
            # Check if message matches FAQ
            faq_answer = _check_free_tier_faq(request.message)
            
            if faq_answer:
                # Return FAQ answer
                ai_response = {
                    'response': faq_answer,
                    'intent': 'chat',
                    'action_data': None
                }
            else:
                # Return upgrade message for non-FAQ queries
                ai_response = {
                    'response': FREE_TIER_UPGRADE_MESSAGE,
                    'intent': 'upgrade_required',
                    'action_data': None
                }
            
            # Save assistant message
            await session_service.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_response['response'],
                intent=ai_response['intent']
            )
            
            response = ChatResponse(
                intent=ai_response['intent'],
                response=ai_response['response'],
                session_id=session_id,
                conversation_id=conversation_id
            )
            
            logger.info(f"Free tier response for business {request.business_id}, session {session_id}")
            return response
        
        # PRO/PREMIUM users: Full AI access
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
            intent=ai_response['intent']
        )
        
        # Build response
        response = ChatResponse(
            intent=ai_response['intent'],
            response=ai_response['response'],
            session_id=session_id,
            conversation_id=conversation_id
        )
        
        # Handle checkout intent with action_data
        if ai_response['intent'] == 'checkout' and ai_response.get('action_data'):
            action_data = ai_response['action_data']
            
            # Create order in database
            try:
                # Generate order number
                order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{datetime.utcnow().strftime('%H%M%S')}"
                
                # Get or create customer
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
                
                # Create order data
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
                    "currency": action_data['currency'],
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
                
                # Insert order into database
                order_result = supabase.table("orders")\
                    .insert(order_data)\
                    .execute()
                
                if order_result.data:
                    order = order_result.data[0]
                    
                    # Update action_data with order_id
                    action_data['order_id'] = order['id']
                    action_data['order_number'] = order['order_number']
                    
                    # Set payment URL
                    response.payment_url = f"/pay.html?biz={request.business_id}&order={order['id']}"
                    
                    logger.info(f"Order created: {order_number} for business {request.business_id}")
                else:
                    logger.error(f"Failed to create order for business {request.business_id}")
                    # Keep action_data but without order_id
                    action_data['error'] = "Failed to create order"
            
            except Exception as e:
                logger.error(f"Error creating order: {str(e)}", exc_info=True)
                action_data['error'] = str(e)
            
            # Set action_data in response
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


@router.get("/conversations/{conversation_id}/history")
async def get_conversation_history_endpoint(
    conversation_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get conversation history (authenticated).
    """
    try:
        # Verify user has access to this conversation
        # This requires checking if the conversation belongs to one of user's businesses
        conversation = supabase.table("conversations")\
            .select("business_id")\
            .eq("id", conversation_id)\
            .execute()
        
        if not conversation.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        business_uuid = conversation.data[0]['business_id']
        
        # Verify ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_uuid)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Get messages
        messages = await session_service.get_conversation_history(
            conversation_id=conversation_id,
            limit=100
        )
        
        return {
            "conversation_id": conversation_id,
            "messages": messages
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching conversation history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch conversation history"
        )