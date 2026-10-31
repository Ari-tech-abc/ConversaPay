"""Server-owned sales facts. A model may select actions, never write financial claims."""
import base64
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import re
import time
from typing import Literal
from urllib.parse import urlsplit
import uuid
from pydantic import BaseModel, ConfigDict, Field
from backend.services.money import money, money_db, multiply_money


class SalesPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent: Literal["recommend", "price", "checkout", "payment_status", "link_expiry", "delivery", "clarify", "handoff"]
    item_key: str = Field(default="", max_length=100)
    quantity: int = Field(default=1, ge=1, le=100)
    budget: str | None = Field(default=None, max_length=24, pattern=r"^\d{1,8}(?:\.\d{1,2})?$")
    fulfillment: Literal["delivery", "pickup", "unspecified"] = "unspecified"


def locale_for(message):
    return "he" if re.search(r"[\u0590-\u05ff]", message) else "en"


def choose(locale, he, en):
    return he if locale == "he" else en


def result(text, intent="chat", action_data=None):
    return {"response":text, "intent":intent, "action_data":action_data}


def safe_url(value):
    if not isinstance(value,str) or any(c.isspace() for c in value):
        return None
    try:
        u = urlsplit(value)
        return value if u.scheme == "https" and u.hostname and not u.username and not u.password else None
    except ValueError:
        return None


def safe_amount(value):
    try:
        raw = Decimal(str(value))
        return money(raw) if raw.is_finite() and 0 <= raw <= Decimal("100000000") else None
    except (InvalidOperation,ValueError,TypeError):
        return None


def scoped_products(products, business_id):
    return [p for p in products if str(p.get("business_id")) == str(business_id)
            and p.get("is_active") is True and safe_amount(p.get("price")) is not None
            and str(p.get("currency","ILS")).upper() == "ILS"]


def in_stock(product, quantity):
    try:
        count = int(product.get("inventory_count",-1))
        return count < 0 or count >= quantity
    except (TypeError,ValueError):
        return False


def delivery_fee(settings, mode):
    key = {"delivery":"shipping_ils", "pickup":"pickup_ils"}.get(mode)
    return safe_amount(settings.get(key)) if key and key in settings else None


def quote(product, quantity, settings, mode):
    fee = delivery_fee(settings,mode)
    if fee is None or not in_stock(product,quantity):
        return None
    subtotal = multiply_money(product["price"],quantity)
    return {"product_id":str(product["id"]),"item_key":str(product["item_key"]),"product_name":str(product["name"]),
            "quantity":quantity,"unit_price":money_db(product["price"]),"subtotal":money_db(subtotal),
            "shipping":money_db(fee),"total":money_db(subtotal+fee),"currency":"ILS","fulfillment":mode}


def quote_text(q, locale):
    mode = choose(locale,"משלוח" if q["fulfillment"] == "delivery" else "איסוף עצמי",
                  "delivery" if q["fulfillment"] == "delivery" else "pickup")
    return choose(locale,
        f'{q["product_name"]}, כמות {q["quantity"]}: {q["subtotal"]} ₪; {mode}: {q["shipping"]} ₪; סה״כ {q["total"]} ₪.',
        f'{q["product_name"]}, quantity {q["quantity"]}: {q["subtotal"]} ILS; {mode}: {q["shipping"]} ILS; total {q["total"]} ILS.')


def render_plan(plan, products, business_id, settings, message):
    locale = locale_for(message)
    products = scoped_products(products,business_id)
    if plan.intent in {"payment_status","link_expiry"}:
        return result(choose(locale,"אין כרגע תוצאת שרת מאומתת לבקשה. נציג יכול לבדוק.",
                             "No verified server result is available for that request. A representative can check."),plan.intent)
    if plan.intent == "handoff":
        return result(choose(locale,"נדרשת בדיקת נציג. אין כאן הרשאה לבצע פעולה או לחשוף מידע של עסק אחר.",
                             "A representative needs to review this. There is no authorization here to perform that action or disclose another business's data."))
    if plan.intent == "delivery":
        days = settings.get("shipping_business_days")
        if isinstance(days,list) and len(days) == 2 and all(type(d) is int and 0 <= d <= 365 for d in days) and days[0] <= days[1]:
            return result(choose(locale,f"זמן משלוח משוער: {days[0]}–{days[1]} ימי עסקים. זה אינו תוקף קישור תשלום.",
                                 f"Estimated delivery: {days[0]}–{days[1]} business days. This is not a payment link expiry."))
        return result(choose(locale,"לא נמסר זמן משלוח מאומת. נציג יכול לברר.","No verified delivery estimate was supplied. A representative can check."))
    if plan.intent == "clarify":
        return result(choose(locale,"איזה מוצר תרצה, ובאיזו כמות? אפשר לציין גם תקציב ואיסוף או משלוח.",
                             "Which item and quantity would you like? You can also specify a budget and pickup or delivery."))
    selected = next((p for p in products if str(p["item_key"]) == plan.item_key),None)
    if plan.intent in {"price","checkout"}:
        if selected is None:
            return result(choose(locale,"לא נמצא מוצר תואם בקטלוג שהוחזר. איזה מוצר תרצה?",
                                 "No matching item was found in the returned catalog. Which item would you like?"))
        if not in_stock(selected,plan.quantity):
            return result(choose(locale,"הכמות המבוקשת אינה זמינה במלאי. תרצה לבדוק כמות אחרת?",
                                 "The requested quantity is not available. Would you like to check a different quantity?"))
        if plan.intent == "price":
            return result(choose(locale,f'{selected["name"]}: {money_db(selected["price"])} ₪ ליחידה, לפני משלוח או איסוף.',
                                 f'{selected["name"]}: {money_db(selected["price"])} ILS per unit, before delivery or pickup fees.'))
        q = quote(selected,plan.quantity,settings,plan.fulfillment)
        if q is None:
            return result(choose(locale,"לפני רכישה צריך לבחור איסוף או משלוח ולוודא את העלות. לא נמסרה עלות מאומתת לאפשרות שנבחרה.",
                                 "Before purchasing, choose pickup or delivery and confirm its fee. No verified fee was supplied for the selected option."))
        return result(quote_text(q,locale)+choose(locale," לאשר את ההצעה?"," Confirm this quote?"),"quote",q)
    budget = safe_amount(plan.budget) if plan.budget is not None else None
    amounts = [safe_amount(n.replace(",","")) for n in re.findall(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d{1,2})?(?![\w.])",message)]
    if plan.budget is not None and (budget is None or budget not in amounts):
        return result(choose(locale,"מה התקציב הכולל שלך, ואיסוף או משלוח?","What is your total budget, and would you like pickup or delivery?"))
    if budget is not None and delivery_fee(settings,plan.fulfillment) is None:
        return result(choose(locale,"כדי לבדוק התאמה לתקציב צריך אופן קבלה ועלות מאומתת של משלוח או איסוף.",
                             "To check your budget I need the collection method and a verified delivery or pickup fee."))
    candidates = [p for p in products if in_stock(p,plan.quantity)]
    if budget is not None:
        candidates = [p for p in candidates if Decimal(quote(p,plan.quantity,settings,plan.fulfillment)["total"]) <= budget]
    candidates.sort(key=lambda p:(money(p["price"]),str(p["item_key"])))
    if not candidates:
        return result(choose(locale,"לא נמצאה אפשרות זמינה בתקציב בקטלוג שנבדק. אפשר לבדוק מוצרים נוספים או לשנות את התקציב.",
                             "No available option fits the budget in the catalog checked. We can check more products or adjust the budget."))
    if budget is not None:
        return result(quote_text(quote(candidates[0],plan.quantity,settings,plan.fulfillment),locale)
                      +choose(locale," עומד בתקציב. מתאים לך?"," This fits your budget. Would it suit you?"))
    names = "; ".join(f'{p["name"]}: {money_db(p["price"])} ILS' for p in candidates[:3])
    return result(names+choose(locale," — מחירי יחידה לפני משלוח. מה התקציב שלך?"," — unit prices before delivery. What is your budget?"))


def create_confirmation(q, business_id, conversation_id, secret, now=None):
    now = int(time.time()) if now is None else now
    payload = {"b":str(business_id),"c":str(conversation_id),"q":q,"exp":now+600,"nonce":uuid.uuid4().hex}
    body = base64.urlsafe_b64encode(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).decode().rstrip("=")
    return body+"."+hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest()


def verify_confirmation(token, business_id, conversation_id, secret, now=None):
    try:
        body,signature = token.rsplit(".",1)
        if not hmac.compare_digest(hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest(),signature):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(body+"="*((4-len(body)%4)%4)))
        now = int(time.time()) if now is None else now
        if data["b"] != str(business_id) or data["c"] != str(conversation_id) or data["exp"] <= now:
            raise ValueError()
        return data
    except (ValueError,TypeError,KeyError,UnicodeError):
        raise ValueError("Invalid or expired quote confirmation") from None


def checkout_text(url, total, currency, locale):
    if safe_url(url) is None or safe_amount(total) is None:
        return result(choose(locale,"לא התקבלו פרטי תשלום תקינים מהשרת. נציג יכול לבדוק.",
                             "Valid checkout details were not returned by the server. A representative can check."),"error")
    return result(choose(locale,f"קישור לתשלום {money_db(total)} {currency}: {url}\nהתשלום עדיין ממתין לאישור. לא נמסר תוקף מאומת לקישור.",
                         f"Pay {money_db(total)} {currency} here: {url}\nPayment is pending. No verified expiry was supplied for this link."),"checkout")
