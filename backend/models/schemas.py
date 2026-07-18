"""
Pydantic models/schemas for request/response validation.
All models include full type hints for type safety.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from enum import Enum


# ============================================
# Enums
# ============================================

class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


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


# ============================================
# Business Models
# ============================================

class BusinessBase(BaseModel):
    """Base business model with common fields."""
    business_id: str = Field(..., min_length=3, max_length=50, pattern="^[a-z0-9_]+$")
    business_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class BusinessCreate(BusinessBase):
    """Schema for creating a new business."""
    pass


class BusinessUpdate(BaseModel):
    """Schema for updating a business."""
    business_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class BusinessResponse(BusinessBase):
    """Schema for business response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    owner_id: str
    subscription_tier: SubscriptionTier
    subscription_status: SubscriptionStatus
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    settings: Dict[str, Any] = {}
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ============================================
# Product Models
# ============================================

class ProductBase(BaseModel):
    """Base product model."""
    item_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    currency: str = Field(default="ILS", min_length=3, max_length=3)
    image_url: Optional[str] = None
    is_active: bool = True
    inventory_count: int = -1  # -1 means unlimited
    metadata: Dict[str, Any] = {}


class ProductCreate(ProductBase):
    """Schema for creating a product."""
    business_id: str


class ProductUpdate(BaseModel):
    """Schema for updating a product."""
    item_key: Optional[str] = Field(None, min_length=1, max_length=100)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    inventory_count: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class ProductResponse(ProductBase):
    """Schema for product response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    business_id: str
    created_at: datetime
    updated_at: datetime


# ============================================
# Customer Models
# ============================================

class CustomerBase(BaseModel):
    """Base customer model."""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    metadata: Dict[str, Any] = {}


class CustomerCreate(CustomerBase):
    """Schema for creating a customer."""
    business_id: str


class CustomerUpdate(BaseModel):
    """Schema for updating a customer."""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class CustomerResponse(CustomerBase):
    """Schema for customer response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    business_id: str
    total_purchases: float
    purchase_count: int
    last_purchase_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ============================================
# Conversation Models
# ============================================

class ConversationBase(BaseModel):
    """Base conversation model."""
    channel: ChannelType = ChannelType.WEB
    status: ConversationStatus = ConversationStatus.ACTIVE
    metadata: Dict[str, Any] = {}


class ConversationCreate(ConversationBase):
    """Schema for creating a conversation."""
    business_id: str
    session_id: str
    customer_id: Optional[str] = None


class ConversationUpdate(BaseModel):
    """Schema for updating a conversation."""
    customer_id: Optional[str] = None
    status: Optional[ConversationStatus] = None
    ended_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class ConversationResponse(ConversationBase):
    """Schema for conversation response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    business_id: str
    customer_id: Optional[str] = None
    session_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ============================================
# Message Models
# ============================================

class MessageBase(BaseModel):
    """Base message model."""
    role: MessageRole
    content: str = Field(..., min_length=1)
    intent: Optional[str] = None
    metadata: Dict[str, Any] = {}


class MessageCreate(MessageBase):
    """Schema for creating a message."""
    conversation_id: str


class MessageResponse(MessageBase):
    """Schema for message response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    conversation_id: str
    created_at: datetime


# ============================================
# Order Models
# ============================================

class OrderItem(BaseModel):
    """Order item model."""
    product_id: Optional[str] = None
    item_key: str
    name: str
    quantity: int = Field(..., ge=1)
    price: float = Field(..., ge=0)


class OrderBase(BaseModel):
    """Base order model."""
    status: OrderStatus = OrderStatus.PENDING
    subtotal: float = Field(..., ge=0)
    tax: float = Field(default=0, ge=0)
    total: float = Field(..., ge=0)
    currency: str = Field(default="ILS", min_length=3, max_length=3)
    items: List[OrderItem]
    customer_info: Dict[str, Any] = {}
    shipping_address: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class OrderCreate(OrderBase):
    """Schema for creating an order."""
    business_id: str
    customer_id: Optional[str] = None
    conversation_id: Optional[str] = None


class OrderUpdate(BaseModel):
    """Schema for updating an order."""
    status: Optional[OrderStatus] = None
    notes: Optional[str] = None


class PaymentInfo(BaseModel):
    """Payment info for marking orders as paid."""
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None


class OrderResponse(OrderBase):
    """Schema for order response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    business_id: str
    customer_id: Optional[str] = None
    conversation_id: Optional[str] = None
    order_number: str
    created_at: datetime
    updated_at: datetime


# ============================================
# Subscription Models
# ============================================

class SubscriptionCreate(BaseModel):
    """Schema for creating a subscription checkout session."""
    user_id: str
    email: EmailStr
    full_name: Optional[str] = None


class SubscriptionResponse(BaseModel):
    """Schema for subscription response."""
    model_config = ConfigDict(from_attributes=True)
    
    session_id: str
    url: str


# ============================================
# Payment Models
# ============================================

class PaymentBase(BaseModel):
    """Base payment model."""
    amount: float = Field(..., ge=0)
    currency: str = Field(default="ILS", min_length=3, max_length=3)
    status: PaymentStatus = PaymentStatus.PENDING
    payment_method: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    metadata: Dict[str, Any] = {}


class PaymentCreate(PaymentBase):
    """Schema for creating a payment."""
    business_id: str
    order_id: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    stripe_session_id: Optional[str] = None


class PaymentResponse(PaymentBase):
    """Schema for payment response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    business_id: str
    order_id: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    stripe_session_id: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ============================================
# Chat Models
# ============================================

class ChatRequest(BaseModel):
    """Schema for chat request."""
    message: str = Field(..., min_length=1)
    business_id: str
    session_id: Optional[str] = None
    customer_info: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Schema for chat response."""
    intent: str  # "chat", "checkout", or "error"
    response: str
    payment_url: Optional[str] = None
    session_id: str
    conversation_id: Optional[str] = None
    action_data: Optional[Dict[str, Any]] = None  # Structured action data for checkout


# ============================================
# Profile Models (User Subscription Status)
# ============================================

class ProfileBase(BaseModel):
    """Base profile model."""
    email: EmailStr
    full_name: Optional[str] = None


class ProfileCreate(ProfileBase):
    """Schema for creating a profile."""
    user_id: str


class ProfileUpdate(BaseModel):
    """Schema for updating a profile."""
    full_name: Optional[str] = None
    is_pro: Optional[bool] = None
    subscription_expires_at: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None


class ProfileResponse(ProfileBase):
    """Schema for profile response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    user_id: str
    is_pro: bool
    subscription_expires_at: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ============================================
# Auth Models
# ============================================

class UserRegister(BaseModel):
    """Schema for user registration."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    business_name: str = Field(..., min_length=1, max_length=255)


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Schema for token response."""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""
    email: EmailStr


class PasswordReset(BaseModel):
    """Schema for password reset."""
    token: str
    new_password: str = Field(..., min_length=8)


# ============================================
# Log Models
# ============================================

class LogCreate(BaseModel):
    """Schema for creating a log entry."""
    level: LogLevel
    source: str
    message: str
    details: Dict[str, Any] = {}
    business_id: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None


class LogResponse(BaseModel):
    """Schema for log response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    business_id: Optional[str] = None
    level: LogLevel
    source: str
    message: str
    details: Dict[str, Any] = {}
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime


# ============================================
# API Key Models
# ============================================

class ApiKeyBase(BaseModel):
    """Base API key model."""
    name: str = Field(..., min_length=1, max_length=255)
    permissions: List[str] = ["read"]
    expires_at: Optional[datetime] = None


class ApiKeyCreate(ApiKeyBase):
    """Schema for creating an API key."""
    business_id: str


class ApiKeyResponse(ApiKeyBase):
    """Schema for API key response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    business_id: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime


class ApiKeyWithSecret(ApiKeyResponse):
    """Schema for API key response with the actual key (only shown once on creation)."""
    key: str  # Full API key, only shown once


# ============================================
# Webhook Models
# ============================================

class WebhookBase(BaseModel):
    """Base webhook model."""
    url: str = Field(..., min_length=1)
    events: List[str] = []
    secret: Optional[str] = None
    is_active: bool = True


class WebhookCreate(WebhookBase):
    """Schema for creating a webhook."""
    business_id: str


class WebhookUpdate(BaseModel):
    """Schema for updating a webhook."""
    url: Optional[str] = Field(None, min_length=1)
    events: Optional[List[str]] = None
    secret: Optional[str] = None
    is_active: Optional[bool] = None


class WebhookResponse(WebhookBase):
    """Schema for webhook response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    business_id: str
    last_triggered_at: Optional[datetime] = None
    failure_count: int
    created_at: datetime
    updated_at: datetime


# ============================================
# Dashboard/Stats Models
# ============================================

class DashboardStats(BaseModel):
    """Schema for dashboard statistics."""
    total_conversations: int
    total_messages: int
    total_orders: int
    total_revenue: float
    total_customers: int
    conversion_rate: float
    period_days: int


class RevenueStats(BaseModel):
    """Schema for revenue statistics."""
    total_revenue: float
    revenue_by_day: List[Dict[str, Any]]
    period_days: int


class OrderStats(BaseModel):
    """Schema for order statistics."""
    total_orders: int
    orders_by_status: Dict[str, int]
    average_order_value: float
    period_days: int