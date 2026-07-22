from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from enum import Enum

class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"

class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"

class ChannelType(str, Enum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    API = "api"

class ConversationStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELED = "canceled"
    REFUNDED = "refunded"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"

class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class BusinessBase(BaseModel):
    business_id: str = Field(..., min_length=3, max_length=50, pattern="^[a-z0-9_]+$")
    business_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
class BusinessCreate(BusinessBase): pass
class BusinessUpdate(BaseModel):
    business_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
class BusinessResponse(BusinessBase):
    model_config = ConfigDict(from_attributes=True)
    id: str; owner_id: str; subscription_tier: SubscriptionTier; subscription_status: SubscriptionStatus; settings: Dict[str, Any] = {}; is_active: bool; created_at: datetime; updated_at: datetime

class ProductBase(BaseModel):
    item_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    currency: str = Field(default="ILS", min_length=3, max_length=3)
    image_url: Optional[str] = None
    payment_link: Optional[str] = None
    is_active: bool = True
    inventory_count: int = -1
    metadata: Dict[str, Any] = {}
class ProductCreate(ProductBase): business_id: str
class ProductUpdate(BaseModel):
    item_key: Optional[str] = Field(None, min_length=1, max_length=100); name: Optional[str] = Field(None, min_length=1, max_length=255); description: Optional[str] = None; price: Optional[float] = Field(None, ge=0); currency: Optional[str] = Field(None, min_length=3, max_length=3); image_url: Optional[str] = None; payment_link: Optional[str] = None; is_active: Optional[bool] = None; inventory_count: Optional[int] = None; metadata: Optional[Dict[str, Any]] = None
class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: str; business_id: str; created_at: datetime; updated_at: datetime

class CustomerBase(BaseModel):
    email: Optional[EmailStr] = None; phone: Optional[str] = None; name: Optional[str] = None; metadata: Dict[str, Any] = {}
class CustomerCreate(CustomerBase): business_id: str
class CustomerUpdate(BaseModel): email: Optional[EmailStr] = None; phone: Optional[str] = None; name: Optional[str] = None; metadata: Optional[Dict[str, Any]] = None
class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: str; business_id: str; total_purchases: float; purchase_count: int; last_purchase_at: Optional[datetime] = None; created_at: datetime; updated_at: datetime

class ConversationBase(BaseModel): channel: ChannelType = ChannelType.WEB; status: ConversationStatus = ConversationStatus.ACTIVE; metadata: Dict[str, Any] = {}
class ConversationCreate(ConversationBase): business_id: str; session_id: str; customer_id: Optional[str] = None
class ConversationUpdate(BaseModel): customer_id: Optional[str] = None; status: Optional[ConversationStatus] = None; ended_at: Optional[datetime] = None; metadata: Optional[Dict[str, Any]] = None
class ConversationResponse(ConversationBase):
    model_config = ConfigDict(from_attributes=True)
    id: str; business_id: str; customer_id: Optional[str] = None; session_id: str; started_at: datetime; ended_at: Optional[datetime] = None; created_at: datetime; updated_at: datetime

class MessageBase(BaseModel): role: MessageRole; content: str = Field(..., min_length=1); intent: Optional[str] = None; metadata: Dict[str, Any] = {}
class MessageCreate(MessageBase): conversation_id: str
class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True)
    id: str; conversation_id: str; created_at: datetime

class OrderItem(BaseModel): product_id: Optional[str] = None; item_key: str; name: str; quantity: int = Field(..., ge=1); price: float = Field(..., ge=0)
class OrderBase(BaseModel): status: OrderStatus = OrderStatus.PENDING; subtotal: float = Field(..., ge=0); tax: float = Field(default=0, ge=0); total: float = Field(..., ge=0); currency: str = Field(default="ILS", min_length=3, max_length=3); items: List[OrderItem]; customer_info: Dict[str, Any] = {}; shipping_address: Optional[Dict[str, Any]] = None; notes: Optional[str] = None
class OrderCreate(OrderBase): business_id: str; customer_id: Optional[str] = None; conversation_id: Optional[str] = None
class OrderUpdate(BaseModel): status: Optional[OrderStatus] = None; notes: Optional[str] = None
class PaymentInfo(BaseModel): customer_email: Optional[str] = None; customer_name: Optional[str] = None
class OrderResponse(OrderBase):
    model_config = ConfigDict(from_attributes=True)
    id: str; business_id: str; customer_id: Optional[str] = None; conversation_id: Optional[str] = None; order_number: str; created_at: datetime; updated_at: datetime

class SubscriptionCreate(BaseModel): user_id: str; email: EmailStr; full_name: Optional[str] = None; plan_type: str = "pro"
class SubscriptionResponse(BaseModel): model_config = ConfigDict(from_attributes=True); session_id: str; url: str; payme_sale_id: Optional[str] = None
class PaymentBase(BaseModel): amount: float = Field(..., ge=0); currency: str = Field(default="ILS", min_length=3, max_length=3); status: PaymentStatus = PaymentStatus.PENDING; payment_method: Optional[str] = None; customer_email: Optional[str] = None; customer_name: Optional[str] = None; metadata: Dict[str, Any] = {}
class PaymentCreate(PaymentBase): business_id: str; order_id: Optional[str] = None
class PaymentResponse(PaymentBase):
    model_config = ConfigDict(from_attributes=True)
    id: str; business_id: str; order_id: Optional[str] = None; paid_at: Optional[datetime] = None; created_at: datetime; updated_at: datetime

class ChatRequest(BaseModel): message: str = Field(..., min_length=1, max_length=2000); business_id: str; session_id: Optional[str] = Field(None, max_length=128, pattern=r'^[a-zA-Z0-9_\-]{1,128}$'); customer_info: Optional[Dict[str, Any]] = None
class ChatResponse(BaseModel): intent: str; response: str; payment_url: Optional[str] = None; session_id: str; conversation_id: Optional[str] = None; action_data: Optional[Dict[str, Any]] = None
class ProfileBase(BaseModel): email: EmailStr; full_name: Optional[str] = None
class ProfileCreate(ProfileBase): user_id: str
class ProfileUpdate(BaseModel): full_name: Optional[str] = None; plan_type: Optional[str] = None; subscription_expires_at: Optional[datetime] = None; whatsapp_phone_number_id: Optional[str] = None; whatsapp_access_token: Optional[str] = None; whatsapp_verify_token: Optional[str] = None
class ProfileResponse(ProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: str; user_id: str; plan_type: str = "free"; subscription_expires_at: Optional[datetime] = None; whatsapp_phone_number_id: Optional[str] = None; whatsapp_access_token: Optional[str] = None; whatsapp_verify_token: Optional[str] = None; created_at: datetime; updated_at: datetime
class UserRegister(BaseModel): email: EmailStr; password: str = Field(..., min_length=8); full_name: str = Field(..., min_length=1, max_length=255); business_name: str = Field(..., min_length=1, max_length=255)
class UserLogin(BaseModel): email: EmailStr; password: str
class TokenResponse(BaseModel): access_token: str; token_type: str = "bearer"; user_id: str; email: str
class PasswordResetRequest(BaseModel): email: EmailStr
class PasswordReset(BaseModel): token: str; new_password: str = Field(..., min_length=8)
class LogCreate(BaseModel): level: LogLevel; source: str; message: str; details: Dict[str, Any] = {}; business_id: Optional[str] = None; user_agent: Optional[str] = None; ip_address: Optional[str] = None
class LogResponse(BaseModel): model_config = ConfigDict(from_attributes=True); id: str; business_id: Optional[str] = None; level: LogLevel; source: str; message: str; details: Dict[str, Any] = {}; user_agent: Optional[str] = None; ip_address: Optional[str] = None; created_at: datetime
class ApiKeyBase(BaseModel): name: str = Field(..., min_length=1, max_length=255); permissions: List[str] = ["read"]; expires_at: Optional[datetime] = None
class ApiKeyCreate(ApiKeyBase): business_id: str
class ApiKeyResponse(ApiKeyBase): model_config = ConfigDict(from_attributes=True); id: str; business_id: str; key_prefix: str; is_active: bool; last_used_at: Optional[datetime] = None; created_at: datetime
class ApiKeyWithSecret(ApiKeyResponse): key: str
class WebhookBase(BaseModel): url: str = Field(..., min_length=1); events: List[str] = []; secret: Optional[str] = None; is_active: bool = True
class WebhookCreate(WebhookBase): business_id: str
class WebhookUpdate(BaseModel): url: Optional[str] = Field(None, min_length=1); events: Optional[List[str]] = None; secret: Optional[str] = None; is_active: Optional[bool] = None
class WebhookResponse(WebhookBase): model_config = ConfigDict(from_attributes=True); id: str; business_id: str; last_triggered_at: Optional[datetime] = None; failure_count: int; created_at: datetime; updated_at: datetime
class AnalyticsOverviewResponse(BaseModel): total_revenue: float = Field(default=0.0); closed_deals_count: int = Field(default=0, ge=0); average_order_value: float = Field(default=0.0, ge=0); total_conversations: int = Field(default=0, ge=0)
class PremiumFeatures(BaseModel): has_whatsapp: bool = False; has_wordpress_plugin: bool = False; has_html_embed: bool = False; domain_limit: int = 1; whitelabel_available: bool = False
class BusinessWidgetData(BaseModel): data: Dict[str, Any]; has_limitations: bool = False; overlay_active: bool = False; overlay_text: str = ""; upgrade_url: str = ""
