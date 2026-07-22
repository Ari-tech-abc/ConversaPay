"""Public AI chat router with three-tier plan enforcement."""
import logging, re, uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Request
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.rate_limiter import check_rate_limit
from backend.models.schemas import ChatRequest, ChatResponse
from backend.services.gemini_service import gemini_service
from backend.services.session_service import session_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, request_obj: Request):
    check_rate_limit(request_obj)
    try:
        is_uuid = bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", request.business_id, re.I))
        query = supabase.table("businesses").select("*").eq("is_active", True)
        business_result = (query.eq("id", request.business_id) if is_uuid else query.eq("business_id", request.business_id)).execute()
        if not business_result.data:
            raise HTTPException(status_code=404, detail="Business not found")
        business = business_result.data[0]
        profile = supabase.table("profiles").select("plan_type").eq("user_id", business["owner_id"]).maybe_single().execute()
        plan_type = (profile.data or {}).get("plan_type", "free")
        can_checkout = plan_type in ("pro", "premium")
        conversation = await session_service.get_or_create_conversation(business_id=business["id"], session_id=request.session_id or f"session_{uuid.uuid4().hex}", channel="web")
        products = supabase.table("products").select("*").eq("business_id", business["id"]).eq("is_active", True).execute().data or []
        customer_context = None
        customer = None
        if request.customer_info:
            customer = await session_service.get_or_create_customer(business_id=business["id"], email=request.customer_info.get("email"), phone=request.customer_info.get("phone"), name=request.customer_info.get("name"))
            if customer:
                customer_context = {"name":customer.get("name"),"email":customer.get("email"),"phone":customer.get("phone"),"purchase_count":customer.get("purchase_count",0),"total_purchases":customer.get("total_purchases",0)}
        history = await session_service.get_conversation_history(conversation_id=conversation["id"], limit=20)
        await session_service.add_message(conversation_id=conversation["id"], role="user", content=request.message)
        answer = await gemini_service.chat(business_id=business["id"], session_id=conversation["session_id"], message=request.message, business_data=business, products=products, customer_context=customer_context, conversation_history=[{"role":m["role"],"content":m["content"]} for m in history])
        if not can_checkout and answer.get("intent") == "checkout":
            answer["intent"] = "upgrade_required"
            answer["response"] = "רכישה בצ׳אט זמינה במסלולי PRO ו-PREMIUM. שדרג כדי להפעיל אותה."
        await session_service.add_message(conversation_id=conversation["id"], role="assistant", content=answer.get("response", ""), intent=answer.get("intent"))
        response = ChatResponse(intent=answer.get("intent", "chat"), response=answer.get("response", ""), session_id=conversation["session_id"], conversation_id=conversation["id"])
        action = answer.get("action_data")
        if answer.get("intent") == "checkout" and action and can_checkout:
            product = next((p for p in products if p.get("item_key") == action.get("item_key")), None)
            if product and product.get("payment_link"):
                response.payment_url = product["payment_link"]
            else:
                quantity = max(1, int(action.get("quantity", 1)))
                price = float(product.get("price", 0)) if product else 0.0
                if not product or price < 0:
                    response.action_data = {**action, "error": "Product unavailable"}
                else:
                    order_data = {"business_id":business["id"],"customer_id":customer.get("id") if customer else None,"conversation_id":conversation["id"],"order_number":f"ORD-{datetime.utcnow():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}","status":"pending","payment_status":"pending","subtotal":round(price*quantity,2),"tax":0,"total":round(price*quantity,2),"currency":product.get("currency","ILS"),"items":[{"product_id":product.get("id"),"item_key":product.get("item_key"),"name":product.get("name"),"quantity":quantity,"price":price}],"customer_info":request.customer_info or {},"created_at":datetime.utcnow().isoformat()}
                    created = supabase.table("orders").insert(order_data).execute()
                    if created.data:
                        order = created.data[0]
                        action.update({"order_id":order["id"],"order_number":order["order_number"]})
                        response.payment_url = f"/pay.html?order_id={order['id']}"
            response.action_data = action
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("Chat endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to process chat message")
