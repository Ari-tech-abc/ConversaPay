import asyncio, logging, re, uuid
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Request
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import active_plan, get_current_user_optional
from backend.middleware.rate_limiter import check_rate_limit, free_chat_session_limiter, free_dashboard_chat_limiter, get_client_ip
from backend.models.schemas import ChatRequest, ChatResponse
from backend.services.gemini_service import gemini_service
from backend.services.payment_adapters import CheckoutOrder, PaymentAdapterError, get_checkout_adapter
from backend.services.session_service import session_service
from backend.services.money import money, money_db, multiply_money
from backend.services.widget_auth import authorize_widget_request
from backend.services.verified_sales import (create_confirmation, verify_confirmation, quote,
    quote_text, checkout_text, safe_url, safe_amount, locale_for, choose, result, scoped_products)

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
    if safe_url(checkout.checkout_url) is None:
        raise PaymentAdapterError("Provider returned an invalid checkout URL")
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


async def _confirmed_checkout(request, business, conversation, customer):
    """Only an authenticated server quote plus a customer click can create checkout."""
    locale = locale_for(request.message)
    try:
        approval = verify_confirmation(request.confirmation_token, business["id"], conversation["id"], settings.SECRET_KEY)
    except ValueError:
        return result(choose(locale,"ההצעה פגה או אינה תקינה. בקש הצעת מחיר חדשה.","This quote expired or is invalid. Please request a new quote."))
    saved = approval["q"]
    product = await _product_by_key(business["id"], saved["item_key"])
    if not product or not scoped_products([product],business["id"]):
        return result(choose(locale,"המוצר אינו זמין עוד. צריך הצעה חדשה.","This item is no longer available. A new quote is needed."))
    fresh = quote(product,saved["quantity"],business.get("settings") or {},saved["fulfillment"])
    if fresh != saved:
        return result(choose(locale,"המחיר, התנאים או המלאי השתנו. צריך הצעה חדשה לפני אישור.",
                             "The price, terms or stock changed. A new quote is needed before confirmation."))
    number = "ORD-" + approval["nonce"]
    def existing_order():
        return supabase.table("orders").select("*").eq("business_id",business["id"]).eq("conversation_id",conversation["id"]).eq("order_number",number).limit(1).execute().data or []
    existing = await asyncio.to_thread(existing_order)
    if existing:
        def payment_for_order():
            return supabase.table("payments").select("*").eq("business_id",business["id"]).eq("order_id",existing[0]["id"]).order("created_at",desc=True).limit(1).execute().data or []
        payments = await asyncio.to_thread(payment_for_order)
        url = (payments[0].get("metadata") or {}).get("checkout_url") if payments else None
        if url and existing[0].get("payment_status") == "pending":
            answer = checkout_text(url,existing[0]["total"],existing[0].get("currency","ILS"),locale)
            answer["payment_url"] = safe_url(url)
            answer["action_data"] = {**saved,"order_id":existing[0]["id"],"order_number":number}
            return answer
        return result(choose(locale,"הבקשה כבר נקלטה. אין אישור ליצור שוב קישור; נציג יכול לבדוק את מצבה.",
                             "This request was already received. I cannot create another checkout; a representative can check its status."))
    data = {"business_id":business["id"],"customer_id":customer.get("id") if customer else None,
            "conversation_id":conversation["id"],"order_number":number,"status":"pending","payment_status":"pending",
            "subtotal":saved["subtotal"],"tax":"0.00","total":saved["total"],"currency":saved["currency"],
            "items":[{"product_id":saved["product_id"],"item_key":saved["item_key"],"name":saved["product_name"],
                      "quantity":saved["quantity"],"price":saved["unit_price"]}],
            "customer_info":request.customer_info or {},"created_at":datetime.utcnow().isoformat()}
    # order_number is unique in the existing schema: concurrent replay cannot insert a second order.
    try:
        created = await asyncio.to_thread(lambda:supabase.table("orders").insert(data).execute())
    except Exception:
        if await asyncio.to_thread(existing_order):
            return result(choose(locale,"הבקשה כבר נקלטה ומטופלת. אין ליצור שוב הזמנה.",
                                 "This request was already received and is being processed. No second order will be created."))
        raise
    if not created.data:
        return result(choose(locale,"לא התקבל אישור ליצירת הזמנה.","Order creation was not confirmed."),"error")
    order = created.data[0]
    try:
        url, session_id, _ = await asyncio.wait_for(_create_order_checkout(order,request.customer_info),timeout=25)
        if safe_url(url) is None:
            raise PaymentAdapterError("Invalid checkout URL")
    except (PaymentAdapterError,asyncio.TimeoutError):
        logger.warning("Checkout not confirmed for order %s",order["id"],exc_info=True)
        return result(choose(locale,"הבקשה נקלטה, אך יצירת קישור התשלום לא אושרה. אין אישור שהתשלום בוצע. נציג יכול לבדוק.",
                             "The request was received, but checkout creation was not confirmed. Payment has not been confirmed. A representative can check."),"error")
    answer = checkout_text(url,saved["total"],saved["currency"],locale)
    answer["payment_url"] = url
    answer["action_data"] = {**saved,"order_id":order["id"],"order_number":number,"provider_session_id":session_id}
    return answer


async def _verified_order_status(business_id, conversation_id, locale):
    def fetch():
        return supabase.table("orders").select("id,total,currency,payment_status").eq("business_id",business_id).eq("conversation_id",conversation_id).order("created_at",desc=True).limit(2).execute().data or []
    orders = await asyncio.to_thread(fetch)
    if len(orders) != 1:
        return result(choose(locale,"לא ניתן לזהות הזמנה אחת בוודאות בשיחה הזו. נציג יכול לבדוק את התשלום.",
                             "I cannot identify a single order with certainty in this conversation. A representative can check the payment."))
    order = orders[0]
    if order.get("payment_status") in {"succeeded","paid"}:
        def matching_payments():
            return supabase.table("payments").select("amount,currency,status,metadata").eq("business_id",business_id).eq("order_id",order["id"]).eq("status","succeeded").limit(10).execute().data or []
        payments = await asyncio.to_thread(matching_payments)
        verified = any(safe_amount(p.get("amount")) is not None
                       and safe_amount(p.get("amount")) == safe_amount(order.get("total"))
                       and str(p.get("currency")).upper() == str(order.get("currency")).upper()
                       and (p.get("metadata") or {}).get("provider") in {"stripe","payme","cardcom"}
                       and (p.get("metadata") or {}).get("provider_session_id") for p in payments)
        if verified:
            return result(choose(locale,f'לפי נתוני השרת, התשלום בסך {money_db(order["total"])} {order["currency"]} אושר.',
                                 f'The server confirms payment of {money_db(order["total"])} {order["currency"]}.'))
    return result(choose(locale,"לפי השרת, אין אישור שהתשלום הושלם. נציג יכול לבדוק; אין צורך לשלם שוב על סמך ההודעה הזו.",
                         "The server has not confirmed completed payment. A representative can check; do not pay again based on this message."))


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
        profile = supabase.table("profiles").select("plan_type,subscription_status,subscription_expires_at,subscription_end_date").eq("user_id", business["owner_id"]).maybe_single().execute()
        plan_type = active_plan(profile.data or {})

        await authorize_widget_request(
            requested_business_id=request.business_id,
            actual_business_id=business["id"],
            plan_type=plan_type,
            request=request_obj,
            client=supabase,
        )

        if plan_type == "free":
            dashboard_user = await get_current_user_optional(request_obj)
            if dashboard_user and str(business.get("owner_id")) == str(dashboard_user.user_id):
                dashboard_key = str(dashboard_user.user_id)
                if not free_dashboard_chat_limiter.is_allowed(dashboard_key):
                    rem = free_dashboard_chat_limiter.remaining(dashboard_key)
                    raise HTTPException(
                        status_code=429,
                        detail={"error": "free_dashboard_limit_reached", "message": "הגעת למגבלת 5 הודעות AI בשעה בדשבורד.", "remaining_requests": rem, "limit": 5},
                        headers={"Retry-After": str(free_dashboard_chat_limiter.window_seconds)},
                    )

        if plan_type == "free":
            # Caller-controlled session IDs must not reset the free demo budget.
            session_key = f"{business['id']}:{get_client_ip(request_obj)}"
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
        if request.confirmation_token:
            if not can_checkout:
                answer = result("רכישה בצ׳אט זמינה במסלולי PRO ו-PREMIUM.","upgrade_required")
            else:
                answer = await _confirmed_checkout(request,business,conversation,customer)
        else:
            answer = await gemini_service.chat(business_id=business["id"], session_id=conversation["session_id"], message=request.message, business_data=business, products=products, customer_context=customer_context, conversation_history=[{"role":m["role"],"content":m["content"]} for m in history])
            if answer.get("intent") == "payment_status":
                answer = await _verified_order_status(business["id"],conversation["id"],locale_for(request.message))
            if answer.get("intent") == "quote":
                if not can_checkout:
                    answer = result(choose(locale_for(request.message),"רכישה בצ׳אט זמינה במסלולי PRO ו-PREMIUM.","Chat checkout is available on PRO and PREMIUM plans."),"upgrade_required")
                else:
                    proposal = answer.get("action_data") or {}
                    # Re-fetch current catalog data before issuing any server approval token.
                    product = await _product_by_key(business["id"],str(proposal.get("item_key","")))
                    fresh = quote(product,proposal.get("quantity",1),business.get("settings") or {},proposal.get("fulfillment")) if product and scoped_products([product],business["id"]) else None
                    if fresh is None:
                        answer = result(choose(locale_for(request.message),"צריך לבדוק מחדש מחיר, אופן קבלה ומלאי לפני רכישה.","Price, collection method and stock must be checked again before checkout."))
                    else:
                        token = create_confirmation(fresh,business["id"],conversation["id"],settings.SECRET_KEY)
                        answer = result(quote_text(fresh,locale_for(request.message))+choose(locale_for(request.message)," לאשר את ההצעה?"," Confirm this quote?"),"quote",{**fresh,"confirmation_token":token,"locale":locale_for(request.message)})
        response = ChatResponse(intent=answer.get("intent","chat"),response=answer.get("response",""),session_id=conversation["session_id"],conversation_id=conversation["id"],payment_url=answer.get("payment_url"),action_data=answer.get("action_data"))
        # Persist the final server-verified reply, not an intermediate model draft.
        await session_service.add_message(conversation_id=conversation["id"],role="assistant",content=response.response,intent=response.intent)
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("Chat endpoint failed"); raise HTTPException(500, "Failed to process chat message")
