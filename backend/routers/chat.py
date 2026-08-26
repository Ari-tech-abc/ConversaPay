import logging, re, uuid
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Request
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import active_plan
from backend.middleware.rate_limiter import check_rate_limit, free_chat_session_limiter
from backend.models.schemas import ChatRequest, ChatResponse
from backend.services.gemini_service import gemini_service
from backend.services.payment_adapters import CheckoutOrder, PaymentAdapterError, get_checkout_adapter
from backend.services.session_service import session_service
from backend.services.money import money, money_db, multiply_money
from backend.services.widget_auth import authorize_widget_request

logger = logging.getLogger(__name__); router = APIRouter(prefix="/chat", tags=["chat"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


async def _create_order_checkout(order: dict, customer_info: dict | None) -> tuple[str, str | None, dict]:
    info = customer_info or {}
    checkout_order = CheckoutOrder(
        order_id=str(order["id"]),
        order_number=str(order.get("order_number") or order["id"]),
        amount=Decimal(str(order.get("total") or "0")),
        currency=str(order.get("currency") or "ILS").upper(),
        items=list(order.get("items") or []),
        customer_email=info.get("email"),
        customer_name=info.get("name"),
        metadata={"business_id": str(order.get("business_id") or "")},
    )
    checkout = await get_checkout_adapter().create_checkout(checkout_order)
    payment = supabase.table("payments").insert({
        "business_id": order["business_id"],
        "order_id": order["id"],
        "amount": order["total"],
        "currency": order.get("currency", "ILS"),
        "status": "pending",
        "customer_email": info.get("email"),
        "customer_name": info.get("name"),
        "metadata": {"provider": checkout.provider, "provider_session_id": checkout.provider_session_id, "checkout_url": checkout.checkout_url},
    }).execute()
    return checkout.checkout_url, checkout.provider_session_id, payment.data[0] if payment.data else {}


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, request_obj: Request):
    # Scoped to business_id: one abusive tenant's traffic can no longer
    # exhaust the shared-IP quota for every other tenant, and a single
    # attacker can't burn Gemini spend across many businesses from one IP
    # without also tripping the per-business limit.
    check_rate_limit(request_obj, extra_key=request.business_id)
    try:
        is_uuid = bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", request.business_id, re.I))
        query = supabase.table("businesses").select("*").eq("is_active", True)
        business_result = (query.eq("id", request.business_id) if is_uuid else query.eq("business_id", request.business_id)).execute()
        if not business_result.data:
            raise HTTPException(404, "Business not found")
        business = business_result.data[0]
        profile = supabase.table("profiles").select("plan_type,subscription_expires_at").eq("user_id", business["owner_id"]).maybe_single().execute()
        plan_type = active_plan(profile.data or {})

        # Authorization is API-key / demo-only. Origin, Referer, and Host
        # headers are attacker-controlled and are never used to grant
        # "internal" trust here — see services/widget_auth.py.
        await authorize_widget_request(
            requested_business_id=request.business_id,
            actual_business_id=business["id"],
            plan_type=plan_type,
            request=request_obj,
            client=supabase,
        )

        # Free-plan widget sessions are capped at 5 messages per hour.
        # Scoped to session_id so each visitor gets their own quota.
        if plan_type == "free" and request.session_id:
            session_key = f"{business['id']}:{request.session_id}"
            remaining = free_chat_session_limiter.remaining(session_key)
            if not free_chat_session_limiter.is_allowed(session_key):
                raise HTTPException(
                    status_code=429,
                    detail={"error": "free_limit_reached", "message": "הגעת למגבלת 5 ההודעות החינמיות לשעה.", "remaining_requests": 0, "retry_after": 3600},
                    headers={"Retry-After": "3600"},
                )

        can_checkout = plan_type in ("pro", "premium")
        conversation = await session_service.get_or_create_conversation(business_id=business["id"], session_id=request.session_id or f"session_{uuid.uuid4().hex}", channel="web")
        products = supabase.table("products").select("*").eq("business_id", business["id"]).eq("is_active", True).execute().data or []
        customer_context = None; customer = None
        if request.customer_info:
            customer = await session_service.get_or_create_customer(business_id=business["id"], email=request.customer_info.get("email"), phone=request.customer_info.get("phone"), name=request.customer_info.get("name"))
            customer_context = {"name": customer.get("name"), "email": customer.get("email"), "phone": customer.get("phone"), "purchase_count": customer.get("purchase_count", 0), "total_purchases": customer.get("total_purchases", 0)} if customer else None
        history = await session_service.get_conversation_history(conversation_id=conversation["id"], limit=20)
        await session_service.add_message(conversation_id=conversation["id"], role="user", content=request.message)
        answer = await gemini_service.chat(business_id=business["id"], session_id=conversation["session_id"], message=request.message, business_data=business, products=products, customer_context=customer_context, conversation_history=[{"role": m["role"], "content": m["content"]} for m in history])
        if not can_checkout and answer.get("intent") == "checkout":
            answer.update({"intent": "upgrade_required", "response": "רכישה בצ׳אט זמינה במסלולי PRO ו-PREMIUM. שדרג כדי להפעיל אותה."})
        await session_service.add_message(conversation_id=conversation["id"], role="assistant", content=answer.get("response", ""), intent=answer.get("intent"))
        response = ChatResponse(intent=answer.get("intent", "chat"), response=answer.get("response", ""), session_id=conversation["session_id"], conversation_id=conversation["id"])
        action = answer.get("action_data")
        if answer.get("intent") == "checkout" and action and can_checkout:
            requested_key = str(action.get("item_key", "")).upper()
            product = next((p for p in products if str(p.get("item_key", "")).upper() == requested_key), None)
            if product and product.get("payment_link"):
                response.payment_url = product["payment_link"]
            elif product:
                quantity = max(1, min(100, int(action.get("quantity", 1))))
                price = money(product.get("price", 0)); total = multiply_money(price, quantity)
                order_data = {"business_id": business["id"], "customer_id": customer.get("id") if customer else None, "conversation_id": conversation["id"], "order_number": f"ORD-{datetime.utcnow():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}", "status": "pending", "payment_status": "pending", "subtotal": money_db(total), "tax": "0.00", "total": money_db(total), "currency": product.get("currency", "ILS"), "items": [{"product_id": product.get("id"), "item_key": product.get("item_key"), "name": product.get("name"), "quantity": quantity, "price": money_db(price)}], "customer_info": request.customer_info or {}, "created_at": datetime.utcnow().isoformat()}
                created = supabase.table("orders").insert(order_data).execute()
                if created.data:
                    order = created.data[0]
                    try:
                        checkout_url, provider_session_id, _ = await _create_order_checkout(order, request.customer_info)
                    except PaymentAdapterError as exc:
                        logger.error("Chat checkout creation failed for order %s: %s", order.get("id"), exc, exc_info=True)
                        raise HTTPException(502, "Unable to create a payment checkout") from exc
                    action.update({"order_id": order["id"], "order_number": order["order_number"], "provider": get_checkout_adapter().provider, "provider_session_id": provider_session_id})
                    response.payment_url = checkout_url
                response.action_data = action
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("Chat endpoint failed"); raise HTTPException(500, "Failed to process chat message")