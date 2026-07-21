"""
Gemini AI service for ConversaPay - simple generate_content, no function calling.
"""
from typing import Optional, Dict, List, Any
import logging
from google import genai

from backend.config import settings

logger = logging.getLogger(__name__)


class GeminiService:

    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash"

    def _build_prompt(
        self,
        business_name: str,
        business_description: str,
        products: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]],
        message: str
    ) -> str:
        catalog = "\n".join(
            f"- {p['name']} | קוד: {p['item_key']} | מחיר: ₪{p['price']}"
            + (f" | {p['description']}" if p.get('description') else "")
            + (f" | לינק תשלום: {p['payment_link']}" if p.get('payment_link') else "")
            for p in products
        ) or "אין מוצרים בקטלוג כרגע"

        history = "\n".join(
            f"{'לקוח' if m['role'] == 'user' else 'סוכן'}: {m['content']}"
            for m in conversation_history[-10:]
        )

        return f"""אתה סוכן מכירות של העסק "{business_name}".
{business_description}

מוצרים זמינים:
{catalog}

כללים:
- ענה רק על מוצרים שמופיעים ברשימה
- כשלקוח רוצה לקנות מוצר שיש לו לינק תשלום, שלח את הלינק ישירות בצ'אט
- כשלמוצר אין לו לינק, ציין את שם המוצר, הקוד והמחיר בפורמט: [CHECKOUT: שם_מוצר | קוד | מחיר]
- תשובות קצרות וברורות בעברית

{f"היסטוריית שיחה:{chr(10)}{history}{chr(10)}" if history else ""}לקוח: {message}
סוכן:"""

    async def chat(
        self,
        business_id: str,
        session_id: str,
        message: str,
        business_data: Dict[str, Any],
        products: List[Dict[str, Any]],
        customer_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        try:
            prompt = self._build_prompt(
                business_name=business_data.get('business_name', 'העסק'),
                business_description=business_data.get('description', ''),
                products=products,
                conversation_history=conversation_history or [],
                message=message
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )

            bot_text = response.text or "איך אוכל לעזור?"

            # Detect checkout intent
            intent = "chat"
            action_data = None
            if "[CHECKOUT:" in bot_text:
                intent = "checkout"
                # Extract checkout info
                try:
                    checkout_part = bot_text.split("[CHECKOUT:")[1].split("]")[0].strip()
                    parts = [p.strip() for p in checkout_part.split("|")]
                    if len(parts) >= 3:
                        product_name = parts[0]
                        item_key = parts[1]
                        price_str = parts[2].replace("₪", "").replace(",", "").strip()
                        price = float(price_str)
                        # Find matching product
                        matched = next((p for p in products if p['item_key'] == item_key), None)
                        if matched:
                            action_data = {
                                "action": "show_checkout",
                                "product_id": matched['id'],
                                "item_key": item_key,
                                "product_name": product_name,
                                "quantity": 1,
                                "total": price,
                                "currency": "ILS"
                            }
                except Exception:
                    intent = "chat"

            return {"response": bot_text, "intent": intent, "action_data": action_data}

        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return {"response": "מצטער, אירעה שגיאה. נסה שוב.", "intent": "error", "action_data": None}

    async def generate_summary(self, conversation_messages):
        try:
            msgs = "\n".join(
                f"{'לקוח' if m['role'] == 'user' else 'סוכן'}: {m['content']}"
                for m in conversation_messages
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=f"סכם שיחה זו ב-2 משפטים:\n{msgs}"
            )
            return response.text
        except Exception as e:
            logger.error(f"Summary error: {e}")
            return "לא ניתן ליצור סיכום"


gemini_service = GeminiService()
