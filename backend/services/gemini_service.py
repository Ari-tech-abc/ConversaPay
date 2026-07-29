from typing import Optional,Dict,List,Any
import logging
from decimal import Decimal,InvalidOperation
from google import genai
from backend.config import settings
from backend.services.money import money_db
logger=logging.getLogger(__name__)
class GeminiService:
    def __init__(self): self.client=genai.Client(api_key=settings.GEMINI_API_KEY); self.model_name="gemini-2.5-flash"
    def _build_prompt(self,business_name,business_description,products,conversation_history,message):
        catalog="\n".join(f"- {p['name']} | קוד: {p['item_key']} | מחיר: ₪{money_db(p['price'])}"+(f" | {p['description']}" if p.get('description') else "")+(f" | לינק תשלום: {p['payment_link']}" if p.get('payment_link') else "") for p in products) or "אין מוצרים בקטלוג כרגע"; history="\n".join(f"{'לקוח' if m['role']=='user' else 'סוכן'}: {m['content']}" for m in conversation_history[-10:]); return f"""אתה סוכן מכירות של העסק \"{business_name}\".\n{business_description}\n\nמוצרים זמינים:\n{catalog}\n\nכללים:\n- ענה רק על מוצרים שמופיעים ברשימה\n- כשלקוח רוצה לקנות מוצר שיש לו לינק תשלום, שלח את הלינק ישירות בצ'אט\n- כשלמוצר אין לו לינק, ציין את שם המוצר, הקוד והמחיר בפורמט: [CHECKOUT: שם_מוצר | קוד | מחיר]\n- תשובות קצרות וברורות בעברית\n\n{f'היסטוריית שיחה:{chr(10)}{history}{chr(10)}' if history else ''}לקוח: {message}\nסוכן:"""
    async def chat(self,business_id,session_id,message,business_data,products,customer_context=None,conversation_history=None):
        try:
            response=self.client.models.generate_content(model=self.model_name,contents=self._build_prompt(business_data.get('business_name','העסק'),business_data.get('description',''),products,conversation_history or [],message)); bot_text=response.text or "איך אוכל לעזור?"; action_data=None; intent="chat"
            if "[CHECKOUT:" in bot_text:
                try:
                    parts=[p.strip() for p in bot_text.split("[CHECKOUT:",1)[1].split("]",1)[0].split("|")]; price=Decimal(parts[2].replace("₪","").replace(",","").strip()); matched=next((p for p in products if p['item_key']==parts[1]),None)
                    if len(parts)>=3 and matched: intent="checkout"; action_data={"action":"show_checkout","product_id":matched['id'],"item_key":parts[1],"product_name":parts[0],"quantity":1,"total":money_db(price),"currency":matched.get("currency","ILS")}
                except (InvalidOperation,IndexError,KeyError): intent="chat"
            return {"response":bot_text,"intent":intent,"action_data":action_data}
        except Exception as e: logger.error("Gemini error: %s",e); return {"response":"מצטער, אירעה שגיאה. נסה שוב.","intent":"error","action_data":None}
    async def generate_summary(self,conversation_messages):
        try:return self.client.models.generate_content(model=self.model_name,contents="סכם שיחה זו ב-2 משפטים:\n"+"\n".join(f"{'לקוח' if m['role']=='user' else 'סוכן'}: {m['content']}" for m in conversation_messages)).text
        except Exception as e: logger.error("Summary error: %s",e); return "לא ניתן ליצור סיכום"
gemini_service=GeminiService()
