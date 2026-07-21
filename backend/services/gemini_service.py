"""
Gemini AI service for ConversaPay.
Handles AI conversations with extended context including customer history,
purchase history, business instructions, and product catalog.
Supports function calling for product search and order creation.
"""
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging
from google import genai
from google.genai import types
import uuid

from backend.config import settings
from backend.services.product_service import product_service

logger = logging.getLogger(__name__)


class GeminiService:
    """Service for interacting with Google Gemini AI."""
    
    def __init__(self):
        """Initialize Gemini client."""
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-1.5-flash"
        
        # Define function declarations for Gemini
        self.search_products_function = types.FunctionDeclaration(
            name="search_products",
            description="Search for products in the catalog based on a query. Use this when the customer asks about available products, wants to see what's available, or is looking for a specific type of product.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="Search query - can be product name, description, or keywords (e.g., 'pizza', 'drink', 'dessert')"
                    )
                },
                required=["query"]
            )
        )
        
        self.create_order_function = types.FunctionDeclaration(
            name="create_order",
            description="Create an order when the customer agrees to purchase a product. Call this ONLY when the customer has confirmed they want to buy a specific product.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "product_id": types.Schema(
                        type=types.Type.STRING,
                        description="The ID of the product to purchase"
                    ),
                    "item_key": types.Schema(
                        type=types.Type.STRING,
                        description="The item key/code of the product to purchase"
                    ),
                    "quantity": types.Schema(
                        type=types.Type.INTEGER,
                        description="Quantity to purchase (default: 1)",
                        default=1
                    )
                },
                required=["product_id", "item_key"]
            )
        )
        
        self.tools = types.Tool(
            function_declarations=[
                self.search_products_function,
                self.create_order_function
            ]
        )
    
    def _build_system_instruction(
        self,
        business_name: str,
        business_description: str,
        products: List[Dict[str, Any]],
        customer_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Build comprehensive system instruction with all available context.
        
        Args:
            business_name: Name of the business
            business_description: Business description and AI instructions
            products: List of active products with keys, names, and prices
            customer_context: Optional customer information and purchase history
            conversation_history: Optional recent conversation history
            
        Returns:
            Formatted system instruction string
        """
        # Build product catalog
        catalog_lines = []
        for product in products:
            line = f"- {product['item_key']}: {product['name']} ({product['price']} ש\"ח)"
            if product.get('description'):
                line += f" - {product['description']}"
            catalog_lines.append(line)
        
        catalog_text = "\n".join(catalog_lines) if catalog_lines else "אין מוצרים בקטלוג כרגע"
        
        # Build system instruction
        instruction = f"""
אתה עוזר מכירות ואדיבות מקצועי עבור העסק '{business_name}'.
תפקידך: לענות ללקוחות, לעזור להם למצוא מוצרים מתאימים, ולסייע בסגירת עסקאות.

## תיאור העסק והנחיות:
{business_description}

## חוקי כוון קריטיים:
1. **קטלוג מוצרים אמיתי בלבד**: מותר לך להציא ולהתייחס אך ורק למוצרים שמופיעים בקטלוג הבא!
2. **אסור להמציא**: אם הלקוח מבקש מוצר או שירות שלא מופיע בקטלוג, אמור בנימוס שאינך מציע זאת כרגע.
3. **מידע מדויק**: אל תמציא מחירים, קודי מוצר או פרטים אחרים. השתמש אך ורק במידע מהקטלוג.
4. **סגנון מקצועי**: דבר בשפה ברורה, אדיבה ומקצועית. התאים את הסגנון לתיאור העסק.

## הקטלוג האמיתי והיחיד:
{catalog_text}
"""
        
        # Add customer context if available
        if customer_context:
            instruction += "\n## מידע על הלקוח:\n"
            
            if customer_context.get('name'):
                instruction += f"- שם: {customer_context['name']}\n"
            
            if customer_context.get('email'):
                instruction += f"- אימייל: {customer_context['email']}\n"
            
            if customer_context.get('phone'):
                instruction += f"- טלפון: {customer_context['phone']}\n"
            
            # Purchase history
            purchase_count = customer_context.get('purchase_count', 0)
            total_purchases = customer_context.get('total_purchases', 0)
            
            if purchase_count > 0:
                instruction += f"\n### היסטוריית רכישות:\n"
                instruction += f"- מספר רכישות קודמות: {purchase_count}\n"
                instruction += f"- סך הכל רכישות: ₪{total_purchases:.2f}\n"
                
                if customer_context.get('last_purchase_at'):
                    last_purchase = customer_context['last_purchase_at']
                    if isinstance(last_purchase, str):
                        last_purchase = datetime.fromisoformat(last_purchase)
                    instruction += f"- רכישה אחרונה: {last_purchase.strftime('%d/%m/%Y')}\n"
            
            # Recent orders
            recent_orders = customer_context.get('recent_orders', [])
            if recent_orders:
                instruction += "\n### הזמנות אחרונות:\n"
                for order in recent_orders[:5]:  # Last 5 orders
                    instruction += f"- הזמנה #{order.get('order_number', 'N/A')}: "
                    instruction += f"₪{order.get('total', 0):.2f}, "
                    instruction += f"סטטוס: {order.get('status', 'unknown')}\n"
        
        # Add conversation history if available
        if conversation_history and len(conversation_history) > 0:
            instruction += "\n## היסטוריית שיחה אחרונה:\n"
            for msg in conversation_history[-10:]:  # Last 10 messages
                role = "לקוח" if msg['role'] == 'user' else "אתה"
                instruction += f"{role}: {msg['content']}\n"
        
        # Add function calling instructions
        instruction += """

## יכולות פעולה:
יש לך שתי פונקציות זמינות:
1. **search_products**: חפש מוצרים בקטלוג לפי שאילתה. השתמש בזה כשהלקוח שואל על מוצרים זמינים.
2. **create_order**: צור הזמנה כשהלקוח מאשר רכישה. השתמש בזה רק כשהלקוח אמר בבירור שהוא רוצה לקנות מוצר ספציפי.

## הוראות מכירה:
- כשהלקוח מבקש לראות מוצרים, השתמש בפונקציה search_products
- הצג את התוצאות בצורה ברורה ומסודרת
- כשהלקוח מאשר רכישה, השתמש בפונקציה create_order עם המוצר המדויק
- אל תנחש מוצרים שלא קיימים - תמיד השתמש בפונקציות לחיפוש ויצירת הזמנה
"""
        
        return instruction
    
    def _handle_search_products(
        self,
        business_id: str,
        query: str
    ) -> str:
        """
        Handle search_products function call.
        
        Args:
            business_id: Business UUID
            query: Search query
            
        Returns:
            Formatted search results
        """
        try:
            products = product_service.search_products(business_id, query, limit=5)
            
            if not products:
                return f"לא נמצאו מוצרים התואמים לחיפוש '{query}'."
            
            result_lines = [f"מצאתי {len(products)} מוצרים התואמים לחיפוש '{query}':\n"]
            
            for i, product in enumerate(products, 1):
                result_lines.append(
                    f"{i}. {product['name']} (קוד: {product['item_key']}) - ₪{product['price']}"
                )
                if product.get('description'):
                    result_lines.append(f"   {product['description']}")
            
            return "\n".join(result_lines)
        
        except Exception as e:
            logger.error(f"Error in search_products handler: {str(e)}", exc_info=True)
            return f"אירעה שגיאה בחיפוש מוצרים: {str(e)}"
    
    def _handle_create_order(
        self,
        business_id: str,
        product_id: str,
        item_key: str,
        quantity: int = 1
    ) -> Dict[str, Any]:
        """
        Handle create_order function call.
        Returns order information for the caller to process.
        
        Args:
            business_id: Business UUID
            product_id: Product UUID
            item_key: Product item key
            quantity: Order quantity
            
        Returns:
            Dict with order creation result
        """
        try:
            # Get product details
            product = product_service.get_product_by_id(business_id, product_id)
            
            if not product:
                return {
                    "success": False,
                    "error": f"מוצר עם מזהה {product_id} לא נמצא"
                }
            
            # Calculate total
            total = product['price'] * quantity
            
            return {
                "success": True,
                "product": product,
                "quantity": quantity,
                "total": total,
                "currency": product.get('currency', 'ILS')
            }
        
        except Exception as e:
            logger.error(f"Error in create_order handler: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"אירעה שגיאה ביצירת הזמנה: {str(e)}"
            }

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
        """
        Send a message to Gemini and get a response with function calling support.
        
        Args:
            business_id: Business identifier (UUID)
            session_id: Unique session identifier for conversation continuity
            message: User's message
            business_data: Business information (name, description)
            products: List of active products
            customer_context: Optional customer information
            conversation_history: Optional recent conversation history
            
        Returns:
            Dict with 'response', 'intent', and optional 'action_data'
        """
        try:
            # Build system instruction with all context
            system_instruction = self._build_system_instruction(
                business_name=business_data.get('business_name', 'העסק'),
                business_description=business_data.get('description', ''),
                products=products,
                customer_context=customer_context,
                conversation_history=conversation_history
            )
            
            # Create chat session with configuration and tools
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=1000,
                tools=self.tools
            )
            
            # Create chat session
            chat = self.client.chats.create(
                model=self.model_name,
                config=config
            )
            
            # Send message and get response
            response = chat.send_message(message)
            
            # Check if model wants to call a function
            action_data = None
            intent = "chat"
            
            # Handle function calls
            if response.function_calls:
                for function_call in response.function_calls:
                    function_name = function_call.name
                    args = function_call.args
                    
                    logger.info(f"Function call requested: {function_name} with args: {args}")
                    
                    if function_name == "search_products":
                        result = self._handle_search_products(business_id, args.get("query", ""))
                        response = chat.send_message(
                            types.Part.from_function_response(
                                name=function_name,
                                response={"result": result}
                            )
                        )
                    
                    elif function_name == "create_order":
                        result = self._handle_create_order(
                            business_id=business_id,
                            product_id=args.get("product_id"),
                            item_key=args.get("item_key"),
                            quantity=args.get("quantity", 1)
                        )
                        
                        if result["success"]:
                            action_data = {
                                "action": "show_checkout",
                                "product_id": result["product"]["id"],
                                "item_key": result["product"]["item_key"],
                                "product_name": result["product"]["name"],
                                "quantity": result["quantity"],
                                "total": result["total"],
                                "currency": result["currency"]
                            }
                            intent = "checkout"
                            response = chat.send_message(
                                types.Part.from_function_response(
                                    name=function_name,
                                    response={"success": True, "order_created": True}
                                )
                            )
                        else:
                            response = chat.send_message(
                                types.Part.from_function_response(
                                    name=function_name,
                                    response={"success": False, "error": result["error"]}
                                )
                            )
            
            # Safely extract text — response.text can be None if the model
            # returned only a function call with no accompanying text part.
            bot_text = ""
            try:
                bot_text = response.text or ""
            except Exception:
                # Fallback: concatenate all text parts manually
                for part in (response.candidates[0].content.parts if response.candidates else []):
                    if hasattr(part, "text") and part.text:
                        bot_text += part.text
            
            if not bot_text:
                bot_text = "הבנתי! איך אוכל לעזור לך עוד?"
            
            logger.info(f"AI response generated for business {business_id}, session {session_id}")
            
            return {
                "response": bot_text,
                "intent": intent,
                "action_data": action_data
            }
        
        except Exception as e:
            logger.error(f"Gemini API error: {type(e).__name__}: {str(e)}", exc_info=True)
            return {
                "response": "מצטער, אירעה שגיאה במערכת. אנא נסה שוב מאוחר יותר.",
                "intent": "error",
                "action_data": None
            }
    
    async def generate_summary(self, conversation_messages: List[Dict[str, str]]) -> str:
        """
        Generate a summary of a conversation.
        Useful for archiving and analytics.
        
        Args:
            conversation_messages: List of messages in the conversation
            
        Returns:
            Summary string
        """
        try:
            prompt = """
            סכם את השיחה הבאה ב-2-3 משפטים, בכתב רוראטי, עם דגש על:
            1. מה היה צורך הלקוח
            2. אילו מוצרים או שירותים נדונו
            3. מה היה התוצאה (רכישה, שאלה, ביטול וכו')
            
            השיחה:
            """
            
            for msg in conversation_messages:
                role = "לקוח" if msg['role'] == 'user' else "סוכן"
                prompt += f"\n{role}: {msg['content']}"
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            return response.text
        
        except Exception as e:
            logger.error(f"Summary generation error: {str(e)}")
            return "לא ניתן ליצור סיכום שיחה"


# Global service instance
gemini_service = GeminiService()