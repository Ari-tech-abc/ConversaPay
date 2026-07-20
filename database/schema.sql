-- ============================================
-- ConversaPay Multi-Tenant SaaS Database Schema
-- Complete Unified Schema for Supabase
-- ============================================
-- This file contains the ENTIRE database architecture
-- Run this in Supabase Dashboard > SQL Editor
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. PROFILES (User Subscription Status)
-- ============================================
-- Must be created BEFORE businesses since businesses reference profiles

DROP TABLE IF EXISTS profiles CASCADE;

CREATE TABLE profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user' CHECK (role IN ('admin', 'user', 'viewer')),
    is_pro BOOLEAN DEFAULT false,
    plan_type VARCHAR(50) DEFAULT 'free' CHECK (plan_type IN ('free', 'pro', 'premium')),
    subscription_expires_at TIMESTAMP WITH TIME ZONE,
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    -- WhatsApp Business integration fields for Premium tier
    whatsapp_phone_number_id VARCHAR(255),
    whatsapp_access_token TEXT,
    whatsapp_verify_token VARCHAR(255),
    email_verified BOOLEAN DEFAULT false,
    email_verification_token VARCHAR(255),
    email_verification_expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Add index for WhatsApp phone number ID
CREATE INDEX idx_profiles_whatsapp_phone_number_id ON profiles(whatsapp_phone_number_id);

-- Add index for plan_type
CREATE INDEX idx_profiles_plan_type ON profiles(plan_type);

CREATE INDEX idx_profiles_user_id ON profiles(user_id);
CREATE INDEX idx_profiles_is_pro ON profiles(is_pro);
CREATE INDEX idx_profiles_stripe_customer_id ON profiles(stripe_customer_id);
CREATE INDEX idx_profiles_stripe_subscription_id ON profiles(stripe_subscription_id);
CREATE INDEX idx_profiles_email_verified ON profiles(email_verified);
CREATE INDEX idx_profiles_email_verification_token ON profiles(email_verification_token);

-- ============================================
-- 2. BUSINESSES (Tenant Root Table)
-- ============================================

DROP TABLE IF EXISTS businesses CASCADE;

CREATE TABLE businesses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id VARCHAR(50) UNIQUE NOT NULL,
    business_name VARCHAR(255) NOT NULL,
    description TEXT,
    owner_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    subscription_tier VARCHAR(50) DEFAULT 'free' CHECK (subscription_tier IN ('free', 'pro', 'enterprise')),
    subscription_status VARCHAR(50) DEFAULT 'active' CHECK (subscription_status IN ('active', 'canceled', 'past_due')),
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    settings JSONB DEFAULT '{}',
    bot_name VARCHAR(255) DEFAULT 'AI Assistant',
    greeting_message TEXT DEFAULT 'Hello! How can I help you today?',
    theme_colors JSONB DEFAULT '{"primary": "#A855F7", "secondary": "#EC4899", "background": "#FFFFFF", "text": "#1F2937"}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_businesses_owner_id ON businesses(owner_id);
CREATE INDEX idx_businesses_business_id ON businesses(business_id);
CREATE INDEX idx_businesses_is_active ON businesses(is_active);
CREATE INDEX idx_businesses_subscription_tier ON businesses(subscription_tier);

-- ============================================
-- 3. PRODUCTS
-- ============================================

DROP TABLE IF EXISTS products CASCADE;

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    item_key VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    currency VARCHAR(3) DEFAULT 'ILS',
    image_url TEXT,
    is_active BOOLEAN DEFAULT true,
    inventory_count INTEGER DEFAULT -1, -- -1 means unlimited
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    UNIQUE(business_id, item_key)
);

CREATE INDEX idx_products_business_id ON products(business_id);
CREATE INDEX idx_products_item_key ON products(item_key);
CREATE INDEX idx_products_is_active ON products(is_active);

-- ============================================
-- 4. CUSTOMERS
-- ============================================

DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    email VARCHAR(255),
    phone VARCHAR(50),
    name VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    total_purchases DECIMAL(10, 2) DEFAULT 0,
    purchase_count INTEGER DEFAULT 0,
    last_purchase_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_customers_business_id ON customers(business_id);
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_phone ON customers(phone);

-- ============================================
-- 5. CONVERSATIONS
-- ============================================

DROP TABLE IF EXISTS conversations CASCADE;

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    channel VARCHAR(50) DEFAULT 'web' CHECK (channel IN ('web', 'whatsapp', 'telegram', 'api')),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'closed', 'archived')),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    ended_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_conversations_business_id ON conversations(business_id);
CREATE INDEX idx_conversations_session_id ON conversations(session_id);
CREATE INDEX idx_conversations_customer_id ON conversations(customer_id);
CREATE INDEX idx_conversations_status ON conversations(status);

-- ============================================
-- 6. MESSAGES
-- ============================================

DROP TABLE IF EXISTS messages CASCADE;

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    intent VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_messages_role ON messages(role);

-- ============================================
-- 7. ORDERS
-- ============================================

DROP TABLE IF EXISTS orders CASCADE;

CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    order_number VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'paid', 'shipped', 'delivered', 'canceled', 'refunded')),
    payment_status VARCHAR(50) DEFAULT 'pending' CHECK (payment_status IN ('pending', 'paid', 'failed', 'refunded')),
    subtotal DECIMAL(10, 2) NOT NULL,
    tax DECIMAL(10, 2) DEFAULT 0,
    total DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'ILS',
    items JSONB NOT NULL, -- Array of {product_id, item_key, name, quantity, price}
    customer_info JSONB DEFAULT '{}',
    shipping_address JSONB,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_orders_business_id ON orders(business_id);
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_payment_status ON orders(payment_status);
CREATE INDEX idx_orders_order_number ON orders(order_number);
CREATE INDEX idx_orders_created_at ON orders(created_at);

-- ============================================
-- 8. PAYMENTS
-- ============================================

DROP TABLE IF EXISTS payments CASCADE;

CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    order_id UUID REFERENCES orders(id) ON DELETE SET NULL,
    stripe_payment_intent_id VARCHAR(255) UNIQUE,
    stripe_session_id VARCHAR(255),
    amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'ILS',
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'succeeded', 'failed', 'canceled', 'refunded')),
    payment_method VARCHAR(50),
    customer_email VARCHAR(255),
    customer_name VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    paid_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_payments_business_id ON payments(business_id);
CREATE INDEX idx_payments_order_id ON payments(order_id);
CREATE INDEX idx_payments_stripe_payment_intent_id ON payments(stripe_payment_intent_id);
CREATE INDEX idx_payments_status ON payments(status);
CREATE INDEX idx_payments_created_at ON payments(created_at);

-- ============================================
-- 9. SUBSCRIPTIONS
-- ============================================

DROP TABLE IF EXISTS subscriptions CASCADE;

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR(255) UNIQUE,
    stripe_price_id VARCHAR(255),
    tier VARCHAR(50) NOT NULL CHECK (tier IN ('free', 'pro', 'enterprise')),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'canceled', 'past_due', 'incomplete', 'incomplete_expired', 'trialing', 'unpaid')),
    current_period_start TIMESTAMP WITH TIME ZONE,
    current_period_end TIMESTAMP WITH TIME ZONE,
    cancel_at_period_end BOOLEAN DEFAULT false,
    canceled_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_subscriptions_business_id ON subscriptions(business_id);
CREATE INDEX idx_subscriptions_stripe_subscription_id ON subscriptions(stripe_subscription_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);

-- ============================================
-- 10. API_KEYS
-- ============================================

DROP TABLE IF EXISTS api_keys CASCADE;

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) UNIQUE NOT NULL,
    key_prefix VARCHAR(20) NOT NULL,
    permissions JSONB DEFAULT '["read"]',
    last_used_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_api_keys_business_id ON api_keys(business_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_is_active ON api_keys(is_active);

-- ============================================
-- 11. WEBHOOKS
-- ============================================

DROP TABLE IF EXISTS webhooks CASCADE;

CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    events JSONB NOT NULL, -- Array of event types
    secret VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    last_triggered_at TIMESTAMP WITH TIME ZONE,
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_webhooks_business_id ON webhooks(business_id);
CREATE INDEX idx_webhooks_is_active ON webhooks(is_active);

-- ============================================
-- 12. LOGS
-- ============================================

DROP TABLE IF EXISTS logs CASCADE;

CREATE TABLE logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
    level VARCHAR(20) NOT NULL CHECK (level IN ('debug', 'info', 'warning', 'error', 'critical')),
    source VARCHAR(50) NOT NULL, -- 'api', 'ai', 'payment', 'webhook', 'system'
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_logs_business_id ON logs(business_id);
CREATE INDEX idx_logs_level ON logs(level);
CREATE INDEX idx_logs_source ON logs(source);
CREATE INDEX idx_logs_created_at ON logs(created_at);

-- ============================================
-- 13. EMAIL_TEMPLATES
-- ============================================

DROP TABLE IF EXISTS email_templates CASCADE;

CREATE TABLE email_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
    template_type VARCHAR(50) NOT NULL, -- 'welcome', 'receipt', 'password_reset', 'order_confirmation'
    subject VARCHAR(255) NOT NULL,
    body_html TEXT NOT NULL,
    body_text TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    UNIQUE(business_id, template_type)
);

CREATE INDEX idx_email_templates_business_id ON email_templates(business_id);
CREATE INDEX idx_email_templates_template_type ON email_templates(template_type);

-- ============================================
-- TRIGGERS FOR UPDATED_AT
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = TIMEZONE('utc'::text, NOW());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to all tables with updated_at
CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_businesses_updated_at BEFORE UPDATE ON businesses FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON products FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_customers_updated_at BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_payments_updated_at BEFORE UPDATE ON payments FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_subscriptions_updated_at BEFORE UPDATE ON subscriptions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_webhooks_updated_at BEFORE UPDATE ON webhooks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_email_templates_updated_at BEFORE UPDATE ON email_templates FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

CREATE OR REPLACE FUNCTION generate_order_number()
RETURNS TEXT AS $$
DECLARE
    order_num TEXT;
BEGIN
    order_num := 'ORD-' || TO_CHAR(NOW(), 'YYYYMMDD') || '-' || LPAD(FLOOR(RANDOM() * 10000)::TEXT, 4, '0');
    RETURN order_num;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- SECURITY TRIGGERS
-- ============================================

-- Prevent non-admin users from updating subscription-related fields
-- This protects against malicious client-side updates even if RLS is bypassed
CREATE OR REPLACE FUNCTION prevent_subscription_field_updates()
RETURNS TRIGGER AS $$
BEGIN
    -- Check if any subscription-related fields are being updated
    IF (NEW.is_pro IS DISTINCT FROM OLD.is_pro) OR
       (NEW.plan_type IS DISTINCT FROM OLD.plan_type) OR
       (NEW.subscription_expires_at IS DISTINCT FROM OLD.subscription_expires_at) OR
       (NEW.stripe_customer_id IS DISTINCT FROM OLD.stripe_customer_id) OR
       (NEW.stripe_subscription_id IS DISTINCT FROM OLD.stripe_subscription_id) THEN
        
        -- Only allow updates from service_role (backend with admin privileges)
        -- auth.role() returns 'service_role' for backend operations using SUPABASE_SERVICE_ROLE_KEY
        -- auth.role() returns 'authenticated' for client-side operations using ANON_KEY
        IF auth.role() != 'service_role' THEN
            RAISE EXCEPTION 'Unauthorized: Subscription fields can only be updated by backend service';
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to profiles table to protect subscription fields
CREATE TRIGGER prevent_profiles_subscription_updates 
    BEFORE UPDATE ON profiles 
    FOR EACH ROW 
    EXECUTE FUNCTION prevent_subscription_field_updates();

-- ============================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================

-- ============================================
-- PROFILES RLS
-- ============================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Users can view their own profile
CREATE POLICY "Users can view their own profile"
ON profiles FOR SELECT
USING (auth.uid() = user_id);

-- Users can insert their own profile
CREATE POLICY "Users can insert their own profile"
ON profiles FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- Users CANNOT directly update profiles via client SDK
-- All profile updates must go through backend API (which uses service_role key)
-- Subscription fields are protected by database trigger

-- ============================================
-- BUSINESSES RLS
-- ============================================

ALTER TABLE businesses ENABLE ROW LEVEL SECURITY;

-- Users can view their own businesses
CREATE POLICY "Users can view their own businesses"
ON businesses FOR SELECT
USING (auth.uid() = owner_id);

-- Users can create their own business (requires Pro subscription - enforced in backend)
CREATE POLICY "Users can create their own business"
ON businesses FOR INSERT
WITH CHECK (auth.uid() = owner_id);

-- Users can update their own businesses
CREATE POLICY "Users can update their own businesses"
ON businesses FOR UPDATE
USING (auth.uid() = owner_id)
WITH CHECK (auth.uid() = owner_id);

-- Users can delete their own businesses
CREATE POLICY "Users can delete their own businesses"
ON businesses FOR DELETE
USING (auth.uid() = owner_id);

-- ============================================
-- PRODUCTS RLS
-- ============================================

ALTER TABLE products ENABLE ROW LEVEL SECURITY;

-- Users can view products from their businesses
CREATE POLICY "Users can view their products"
ON products FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = products.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create products in their businesses
CREATE POLICY "Users can create their products"
ON products FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = products.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can update their products
CREATE POLICY "Users can update their products"
ON products FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = products.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = products.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can delete their products
CREATE POLICY "Users can delete their products"
ON products FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = products.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- CUSTOMERS RLS
-- ============================================

ALTER TABLE customers ENABLE ROW LEVEL SECURITY;

-- Users can view their customers
CREATE POLICY "Users can view their customers"
ON customers FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = customers.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create customers
CREATE POLICY "Users can create their customers"
ON customers FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = customers.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can update their customers
CREATE POLICY "Users can update their customers"
ON customers FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = customers.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = customers.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can delete their customers
CREATE POLICY "Users can delete their customers"
ON customers FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = customers.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- CONVERSATIONS RLS
-- ============================================

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- Users can view their conversations
CREATE POLICY "Users can view their conversations"
ON conversations FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = conversations.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create conversations
CREATE POLICY "Users can create their conversations"
ON conversations FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = conversations.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can update their conversations
CREATE POLICY "Users can update their conversations"
ON conversations FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = conversations.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = conversations.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can delete their conversations
CREATE POLICY "Users can delete their conversations"
ON conversations FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = conversations.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- MESSAGES RLS
-- ============================================

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- Users can view messages from their conversations
CREATE POLICY "Users can view their messages"
ON messages FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM conversations
        JOIN businesses ON businesses.id = conversations.business_id
        WHERE conversations.id = messages.conversation_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create messages
CREATE POLICY "Users can create their messages"
ON messages FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM conversations
        JOIN businesses ON businesses.id = conversations.business_id
        WHERE conversations.id = messages.conversation_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- ORDERS RLS
-- ============================================

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Users can view their orders
CREATE POLICY "Users can view their orders"
ON orders FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = orders.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create orders
CREATE POLICY "Users can create their orders"
ON orders FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = orders.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can update their orders
CREATE POLICY "Users can update their orders"
ON orders FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = orders.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = orders.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can delete their orders
CREATE POLICY "Users can delete their orders"
ON orders FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = orders.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- PAYMENTS RLS
-- ============================================

ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

-- Users can view their payments
CREATE POLICY "Users can view their payments"
ON payments FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = payments.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create payments
CREATE POLICY "Users can create their payments"
ON payments FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = payments.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can update their payments
CREATE POLICY "Users can update their payments"
ON payments FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = payments.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = payments.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- SUBSCRIPTIONS RLS
-- ============================================

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- Users can view their subscriptions
CREATE POLICY "Users can view their subscriptions"
ON subscriptions FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = subscriptions.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create subscriptions
CREATE POLICY "Users can create their subscriptions"
ON subscriptions FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = subscriptions.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can update their subscriptions
CREATE POLICY "Users can update their subscriptions"
ON subscriptions FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = subscriptions.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = subscriptions.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- API_KEYS RLS
-- ============================================

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- Users can view their API keys
CREATE POLICY "Users can view their api_keys"
ON api_keys FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = api_keys.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create API keys
CREATE POLICY "Users can create their api_keys"
ON api_keys FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = api_keys.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can update their API keys
CREATE POLICY "Users can update their api_keys"
ON api_keys FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = api_keys.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = api_keys.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can delete their API keys
CREATE POLICY "Users can delete their api_keys"
ON api_keys FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = api_keys.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- WEBHOOKS RLS
-- ============================================

ALTER TABLE webhooks ENABLE ROW LEVEL SECURITY;

-- Users can view their webhooks
CREATE POLICY "Users can view their webhooks"
ON webhooks FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = webhooks.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create webhooks
CREATE POLICY "Users can create their webhooks"
ON webhooks FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = webhooks.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can update their webhooks
CREATE POLICY "Users can update their webhooks"
ON webhooks FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = webhooks.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = webhooks.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can delete their webhooks
CREATE POLICY "Users can delete their webhooks"
ON webhooks FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = webhooks.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- LOGS RLS
-- ============================================

ALTER TABLE logs ENABLE ROW LEVEL SECURITY;

-- Users can view their logs
CREATE POLICY "Users can view their logs"
ON logs FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = logs.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create logs
CREATE POLICY "Users can create their logs"
ON logs FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = logs.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- EMAIL_TEMPLATES RLS
-- ============================================

ALTER TABLE email_templates ENABLE ROW LEVEL SECURITY;

-- Users can view their email templates
CREATE POLICY "Users can view their email_templates"
ON email_templates FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = email_templates.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can create email templates
CREATE POLICY "Users can create their email_templates"
ON email_templates FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = email_templates.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can update their email templates
CREATE POLICY "Users can update their email_templates"
ON email_templates FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = email_templates.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = email_templates.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Users can delete their email templates
CREATE POLICY "Users can delete their email_templates"
ON email_templates FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = email_templates.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- ============================================
-- END OF SCHEMA
-- ============================================
-- Ready to run in Supabase Dashboard > SQL Editor
-- ============================================