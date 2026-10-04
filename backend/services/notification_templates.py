"""Notification content shared by mail delivery and offline preview tools."""
from html import escape

SECURITY_LABELS = {
    "password_changed": "הסיסמה שלך שונתה.",
    "api_key_created": "נוצר מפתח API חדש בחשבון שלך.",
    "api_key_revoked": "מפתח API בוטל בחשבון שלך.",
    "sessions_revoked": "מכשירים אחרים נותקו מהחשבון שלך.",
}


def render_notification(category: str, payload: dict, frontend_url: str) -> tuple[str, str, str]:
    """Only known fields appear in emails. All event data is escaped in HTML."""
    if category == "payment_success":
        title = "התקבל תשלום חדש"
        body = f"התשלום עבור הזמנה {payload.get('order_number', '')} הושלם.\nסכום: {payload.get('total', '')} {payload.get('currency', '')}"
    elif category == "weekly_digest":
        title = "סיכום הפעילות השבועי שלך"
        period = f"{str(payload.get('period_start', ''))[:10]} עד {str(payload.get('period_end', ''))[:10]} (UTC)"
        revenue = ", ".join(f"{amount} {currency}" for currency, amount in (payload.get("revenue_by_currency") or {}).items()) or "0"
        body = f"{period}\nשיחות חדשות: {payload.get('conversations', 0)}\nהודעות לקוחות: {payload.get('messages', 0)}\nהזמנות חדשות: {payload.get('orders', 0)}\nהזמנות ששולמו: {payload.get('paid_orders', 0)}\nהכנסות: {revenue}"
    elif category == "security_alerts":
        title = "עדכון אבטחה בחשבון שלך"
        body = SECURITY_LABELS.get(payload.get("action"), "בוצעה פעולת אבטחה בחשבון שלך.")
        body += f"\nמועד הפעולה: {payload.get('occurred_at', '')}\nאם לא ביצעת את הפעולה, יש להחליף סיסמה ולפנות לתמיכה."
    elif category == "product_updates":
        title = str(payload.get("title") or "עדכון חדש ב־Talk2Pay").replace("\r", " ").replace("\n", " ")
        body = str(payload.get("body") or "")
    else:
        raise ValueError("Unknown notification category")
    url = frontend_url.rstrip("/") + "/settings#notification-settings"
    text = body + "\n\nהעדפות ההתראות שלך: " + url
    paragraphs = "".join(f'<p style="margin:0 0 12px;line-height:1.8">{escape(line)}</p>' for line in body.splitlines())
    html = f'''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f8faf6;color:#123c31;font-family:Arial,sans-serif;direction:rtl">
    <table role="presentation" width="100%"><tr><td align="center" style="padding:32px 16px">
    <table role="presentation" width="100%" style="max-width:560px;background:white;border:1px solid #dce6dc;border-radius:20px">
    <tr><td style="padding:28px;background:#123c31;color:white"><span>Talk2Pay</span><h1 style="font-size:24px">{escape(title)}</h1></td></tr>
    <tr><td style="padding:28px">{paragraphs}<a href="{escape(url, quote=True)}" style="color:#123c31">ניהול העדפות ההתראות</a></td></tr>
    </table></td></tr></table></body></html>'''
    return title, text, html
