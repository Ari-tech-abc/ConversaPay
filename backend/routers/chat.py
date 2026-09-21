import asyncio, logging, re, uuid
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Request
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import active_plan, get_current_user_optional
from backend.middleware.rate_limiter import check_rate_limit, free_chat_session_limiter, free_dashboard_chat_limiter
from backend.models.schemas import ChatRequest, ChatResponse
from backend.services.gemini_service import gemini_service
from backend.services.payment_adapters import CheckoutOrder, PaymentAdapterError, get_checkout_adapter
from backend.services.session_service import session_service
from backend.services.money import money, money_db, multiply_money
from backend.services.widget_auth import authorize_widget_request

logger = logging.getLogger(__name__); router = APIRouter(prefix="/chat", tags=["chat"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
_PRODUCT_FIELDS = "id,business_id,item_key,name,description,price,currency,image_url,payment_link,is_active,inventory_count,metadata"
_STOP_WORDS = {
    "אני","אתה","אתם","של","על","עם","יש","אם","מה","מי","איך","כמה","אפשר","רוצה","רוצה","צריך","צריכה","לי","לכם","לנו","זה","זאת","את","האם","גם","או","ויש","the","a","an","is","are","do","you","have","with","for","and","or","can","i","want","need","what","how",
}


def _search_terms(message: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_\-\u0590-\u05FF]+", message.lower())
    result: list[str] = []
    for word in words:
        if len(word) < 2 or word in _STOP_WORDS or word in result:
            continue
        result.append(word)
        if len(result) >= 5:
            break
    return result


def _run_product_search(business_id: str, message: str, limit: int = 24) -> list[dict]:
    """Return only a small relevant catalog slice instead of the whole tenant catalog."""
    terms = _search_terms(message)
    found: dict[str, dict] = {}
    try:
        for term in terms:
            # Terms are restricted by _search_terms to letters/digits/_/-, which keeps
            # the PostgREST OR expression safe while still supporting Hebrew and English.
            pattern = f"%{term}%"
            expression = f"name.ilike.{pattern},item_key.ilike.{pattern},description.ilike.{pattern}"
            rows = (
                supabase.table("products")
                .select(_PRODUCT_FIELDS)
                .eq("business_id", business_id)
                .eq("is_active", True)
                .or_(expression)
                .limit(10)
                .execute()
                .data
                or []
            )
            for row in rows:
                found[str(row.get("id"))] = row
                if len(found) >= limit:
                    return list(found.values())[:limit]
    except Exception as exc:
        # A search syntax/provider edge case should not take chat down. Fall back to a
        # bounded catalog sample; never fall back to select-all.
        logger.warning("Relevant product search failed for business %s: %s", business_id, exc)

    if found:
        return list(found.values())[:limit]
    return (
        supabase.table("products")
        .select(_PRODUCT_FIELDS)
        .eq("business_id", business_id)
        .eq("is_active", True)
        .order("item_key")
        .limit(limit)
        .execute()
        .data
        or []
    )


async def _relevant_products(business_id: str, message: str, limit: int = 24) -> list[dict]:
    return await asyncio.to_thread(_run_product_search, business_id, message, limit)


async def _product_by_key(business_id: str, item_key: str) -> dict | None:
    def fetch_product():
        result = (
            supabase.table("products")
            .select(_PRODUCT_FIELDS)
            .eq("business_id", business_id)
            .eq("is_active", True)
            .ilike("item_key", item_key)
            .limit(1)
            .execute()
        )
        return (result.data or [None])[0]
    return await asyncio.to_thread(fetch_product)


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

        await authorize_widget_request(
            requested_business_id=request.business_id,
            actual_business_id=business["id"],
            plan_type=plan_type,
            request=request_obj,
            client=supabase,
        )

        if request_obj.headers.get("X-Talk2Pay-Dashboard") == "1":
            dashboard_user = await get_current_user_optional(request_obj)
            if dashboard_user and str(business.get("owner_id")) == str(dashboard_user.user_id) and plan_type == "free":
                dashboard_key = str(dashboard_user.user_id)
                if not free_dashboard_chat_limiter.is_allowed(dashboard_key):
                    rem = free_dashboard_chat_limiter.remaining(dashboard_key)
                    raise HTTPException(
                        status_code=429,
                        detail={"error": "free_dashboard_limit_reached", "message": "הגעת למגבלת 5 הודעות AI בשעה בדשבורד.", "remaining_requests": rem, "limit": 5},
                        headers={"Retry-After": str(free_dashboard_chat_limiter.window_seconds)},
                    )

        if plan_type == "free" and request.session_id:
            session_key = f"{business['id']}:{request.session_id}"
            if not free_chat_session_limiter.is_allowed(session_key):
                raise HTTPException(
                    status_code=429,
                    detail={"error": "free_limit_reached", "message": "הגעת למגבלת 5 ההודעות החינמיות לשעה.", "remaining_requests": 0, "retry_after": 3600},
                    headers={"Retry-After": "3600"},
                )

        can_checkout = plan_type in ("pro", "premium")
        conversation = await session_service.get_or_create_conversation(business_id=business["id"], session_id=request.session_id or f"session_{uuid.uuid4().hex}", channel="web")
        products = await _relevant_products(business["id"], request.message, limit=24)
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
            requested_key = str(action.get("item_key", "")).strip()
            product = next((p for p in products if str(p.get("item_key", "")).lower() == requested_key.lower()), None)
            if not product and requested_key:
                product = await _product_by_key(business["id"], requested_key)
            if product and product.get("payment_link"):
                response.payment_url = product["payment_link"]
            elif product:
                quantity = max(1, min(100, int(action.get("quantity", 1))))
                inventory = product.get("inventory_count", -1)
                try: inventory = int(inventory)
                except (TypeError, ValueError): inventory = -1
                if inventory == 0:
                    response.intent = "chat"; response.response = "המוצר שבחרת אזל כרגע מהמלאי."; response.action_data = None
                    return response
                if inventory > 0:
                    quantity = min(quantity, inventory)
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
                    action.update({"order_id": order["id"], "order_number": order["order_number"], "provider": get_checkout_adapter().provider, "provider_session_id": provider_session_id, "quantity": quantity})
                    response.payment_url = checkout_url
                response.action_data = action
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("Chat endpoint failed"); raise HTTPException(500, "Failed to process chat message")
