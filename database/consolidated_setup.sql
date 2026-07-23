-- ============================================
-- ConversaPay Consolidated Supabase Setup
-- Single-file setup for a fresh or reset environment
-- Supersedes the fragmented SQL files in /database
-- ============================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- Drop functions first (tables are dropped separately)
-- ============================================
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
DROP FUNCTION IF EXISTS prevent_subscription_field_updates() CASCADE;
DROP FUNCTION IF EXISTS generate_order_number() CASCADE;

-- ============================================
-- Drop tables in reverse dependency order
-- ============================================
DROP TABLE IF EXISTS abuse_reports CASCADE;
DROP TABLE IF EXISTS admin_audit_logs CASCADE;
DROP TABLE IF EXISTS usage_logs CASCADE;
DROP TABLE IF EXISTS domain_restrictions CASCADE;
DROP TABLE IF EXISTS admin_users CASCADE;
DROP TABLE IF EXISTS activity_logs CASCADE;
DROP TABLE IF EXISTS team_members CASCADE;
DROP TABLE IF EXISTS email_templates CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS logs CASCADE;
DROP TABLE IF EXISTS webhooks CASCADE;
DROP TABLE IF EXISTS site_builder_tokens CASCADE;
DROP TABLE IF EXISTS api_keys CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS businesses CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;

-- ============================================
-- Core tenant/auth tables
-- ============================================

CREATE TABLE profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user' CHECK (role IN ('admin', 'user', 'viewer')),
    is_pro BOOLEAN DEFAULT false,
    plan_type VARCHAR(50) DEFAULT 'free' CHECK (plan_type IN ('free', 'pro', 'premium')),
    subscription_expires_at TIMESTAMP WITH TIME ZONE,
    whatsapp_phone_number_id VARCHAR(255),
    whatsapp_access_token TEXT,
    whatsapp_verify_token VARCHAR(255),
    email_verified BOOLEAN DEFAULT false,
    email_verification_token VARCHAR(255),
    email_verification_expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_profiles_user_id ON profiles(user_id);
CREATE INDEX idx_profiles_plan_type ON profiles(plan_type);
CREATE INDEX idx_profiles_email_verified ON profiles(email_verified);
CREATE INDEX idx_profiles_email_verification_token ON profiles(email_verification_token);
CREATE INDEX idx_profiles_whatsapp_phone_number_id ON profiles(whatsapp_phone_number_id);

CREATE TABLE businesses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id VARCHAR(50) UNIQUE NOT NULL,
    business_name VARCHAR(255) NOT NULL,
    description TEXT,
    owner_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    subscription_tier VARCHAR(50) DEFAULT 'free' CHECK (subscription_tier IN ('free', 'pro', 'enterprise')),
    subscription_status VARCHAR(50) DEFAULT 'active' CHECK (subscription_status IN ('active', 'canceled', 'past_due')),
    settings JSONB DEFAULT '{}'::jsonb,
    bot_name VARCHAR(255) DEFAULT 'AI Assistant',
    greeting_message TEXT DEFAULT 'Hello! How can I help you today?',
    theme_colors JSONB DEFAULT '{"primary":"#A855F7","secondary":"#EC4899","background":"#FFFFFF","text":"#1F2937"}'::jsonb,
    team_size INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_businesses_business_id ON businesses(business_id);
CREATE INDEX idx_businesses_owner_id ON businesses(owner_id);
CREATE INDEX idx_businesses_is_active ON businesses(is_active);
CREATE INDEX idx_businesses_subscription_tier ON businesses(subscription_tier);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    item_key VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    currency VARCHAR(3) DEFAULT 'ILS',
    image_url TEXT,
    payment_link TEXT,
    is_active BOOLEAN DEFAULT true,
    inventory_count INTEGER DEFAULT -1,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    UNIQUE (business_id, item_key)
);

CREATE INDEX idx_products_business_id ON products(business_id);
CREATE INDEX idx_products_item_key ON products(item_key);
CREATE INDEX idx_products_is_active ON products(is_active);

CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    email VARCHAR(255),
    phone VARCHAR(50),
    name VARCHAR(255),
    metadata JSONB DEFAULT '{}'::jsonb,
    total_purchases DECIMAL(10, 2) DEFAULT 0,
    purchase_count INTEGER DEFAULT 0,
    last_purchase_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_customers_business_id ON customers(business_id);
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_phone ON customers(phone);

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    channel VARCHAR(50) DEFAULT 'web' CHECK (channel IN ('web', 'whatsapp', 'telegram', 'api')),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'closed', 'archived')),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    ended_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_conversations_business_id ON conversations(business_id);
CREATE INDEX idx_conversations_customer_id ON conversations(customer_id);
CREATE INDEX idx_conversations_session_id ON conversations(session_id);
CREATE INDEX idx_conversations_status ON conversations(status);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    intent VARCHAR(50),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_messages_created_at ON messages(created_at);

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
    items JSONB NOT NULL,
    customer_info JSONB DEFAULT '{}'::jsonb,
    shipping_address JSONB,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_orders_business_id ON orders(business_id);
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_conversation_id ON orders(conversation_id);
CREATE INDEX idx_orders_order_number ON orders(order_number);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_payment_status ON orders(payment_status);
CREATE INDEX idx_orders_created_at ON orders(created_at);

CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    order_id UUID REFERENCES orders(id) ON DELETE SET NULL,
    payme_sale_id VARCHAR(255) UNIQUE,
    amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'ILS',
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'succeeded', 'failed', 'canceled', 'refunded')),
    payment_method VARCHAR(50),
    customer_email VARCHAR(255),
    customer_name VARCHAR(255),
    metadata JSONB DEFAULT '{}'::jsonb,
    paid_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_payments_business_id ON payments(business_id);
CREATE INDEX idx_payments_order_id ON payments(order_id);
CREATE INDEX idx_payments_status ON payments(status);
CREATE INDEX idx_payments_created_at ON payments(created_at);
CREATE INDEX idx_payments_payme_sale_id ON payments(payme_sale_id);

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    tier VARCHAR(50) NOT NULL CHECK (tier IN ('free', 'pro', 'enterprise')),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'canceled', 'past_due', 'incomplete', 'incomplete_expired', 'trialing', 'unpaid')),
    current_period_start TIMESTAMP WITH TIME ZONE,
    current_period_end TIMESTAMP WITH TIME ZONE,
    cancel_at_period_end BOOLEAN DEFAULT false,
    canceled_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_subscriptions_business_id ON subscriptions(business_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) UNIQUE NOT NULL,
    key_prefix VARCHAR(20) NOT NULL,
    permissions JSONB NOT NULL DEFAULT '["widget"]'::jsonb,
    last_used_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_api_keys_business_id ON api_keys(business_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_is_active ON api_keys(is_active);
CREATE INDEX idx_api_keys_business_active ON api_keys(business_id, is_active);

CREATE TABLE site_builder_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_site_builder_tokens_hash ON site_builder_tokens(token_hash);
CREATE INDEX idx_site_builder_tokens_user_id ON site_builder_tokens(user_id);

CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    events JSONB NOT NULL,
    secret VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    last_triggered_at TIMESTAMP WITH TIME ZONE,
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_webhooks_business_id ON webhooks(business_id);
CREATE INDEX idx_webhooks_is_active ON webhooks(is_active);

CREATE TABLE logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
    level VARCHAR(20) NOT NULL CHECK (level IN ('debug', 'info', 'warning', 'error', 'critical')),
    source VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_logs_business_id ON logs(business_id);
CREATE INDEX idx_logs_level ON logs(level);
CREATE INDEX idx_logs_source ON logs(source);
CREATE INDEX idx_logs_created_at ON logs(created_at);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES profiles(user_id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_logs_ip_address ON audit_logs(ip_address);

CREATE TABLE email_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
    template_type VARCHAR(50) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body_html TEXT NOT NULL,
    body_text TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    UNIQUE (business_id, template_type)
);

CREATE INDEX idx_email_templates_business_id ON email_templates(business_id);
CREATE INDEX idx_email_templates_template_type ON email_templates(template_type);

-- ============================================
-- Team management
-- ============================================

CREATE TABLE team_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(user_id) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'admin', 'manager', 'viewer')),
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'inactive', 'removed')),
    invitation_token VARCHAR(255) UNIQUE,
    invitation_expires_at TIMESTAMP WITH TIME ZONE,
    joined_at TIMESTAMP WITH TIME ZONE,
    permissions JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    UNIQUE (business_id, email)
);

CREATE INDEX idx_team_members_business_id ON team_members(business_id);
CREATE INDEX idx_team_members_user_id ON team_members(user_id);
CREATE INDEX idx_team_members_email ON team_members(email);
CREATE INDEX idx_team_members_status ON team_members(status);
CREATE INDEX idx_team_members_invitation_token ON team_members(invitation_token);

CREATE TABLE activity_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(user_id) ON DELETE SET NULL,
    team_member_id UUID REFERENCES team_members(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    details JSONB DEFAULT '{}'::jsonb,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_activity_logs_business_id ON activity_logs(business_id);
CREATE INDEX idx_activity_logs_user_id ON activity_logs(user_id);
CREATE INDEX idx_activity_logs_created_at ON activity_logs(created_at);

-- ============================================
-- Admin management
-- ============================================

CREATE TABLE admin_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username TEXT,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL CHECK (role IN ('super_admin', 'admin', 'moderator')),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
    last_login TIMESTAMP WITH TIME ZONE,
    login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    two_factor_enabled BOOLEAN DEFAULT false,
    two_factor_secret VARCHAR(255),
    permissions JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_admin_users_email ON admin_users(email);
CREATE INDEX idx_admin_users_status ON admin_users(status);
CREATE INDEX idx_admin_users_role ON admin_users(role);
CREATE UNIQUE INDEX admin_users_username_lower_key ON admin_users (LOWER(username)) WHERE username IS NOT NULL;

CREATE TABLE domain_restrictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    domain VARCHAR(255) NOT NULL,
    installation_id UUID,
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'blocked', 'flagged', 'warning')),
    reason_for_status TEXT,
    max_domains_allowed INTEGER DEFAULT 1,
    current_domain_count INTEGER DEFAULT 0,
    monthly_api_calls_limit INTEGER DEFAULT 100000,
    current_monthly_api_calls INTEGER DEFAULT 0,
    monthly_reset_date DATE,
    blocked_at TIMESTAMP WITH TIME ZONE,
    blocked_by_admin_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_domain_restrictions_business_id ON domain_restrictions(business_id);
CREATE INDEX idx_domain_restrictions_domain ON domain_restrictions(domain);
CREATE INDEX idx_domain_restrictions_status ON domain_restrictions(status);
CREATE INDEX idx_domain_restrictions_created_at ON domain_restrictions(created_at);

CREATE TABLE usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    domain VARCHAR(255),
    endpoint VARCHAR(255),
    method VARCHAR(10),
    status_code INTEGER,
    response_time_ms INTEGER,
    tokens_used INTEGER DEFAULT 0,
    cost_usd DECIMAL(10, 4) DEFAULT 0,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_usage_logs_business_id ON usage_logs(business_id);
CREATE INDEX idx_usage_logs_domain ON usage_logs(domain);
CREATE INDEX idx_usage_logs_created_at ON usage_logs(created_at);

CREATE TABLE admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admin_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    business_id UUID REFERENCES businesses(id) ON DELETE SET NULL,
    details JSONB DEFAULT '{}'::jsonb,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_admin_audit_logs_admin_id ON admin_audit_logs(admin_id);
CREATE INDEX idx_admin_audit_logs_action ON admin_audit_logs(action);
CREATE INDEX idx_admin_audit_logs_business_id ON admin_audit_logs(business_id);
CREATE INDEX idx_admin_audit_logs_created_at ON admin_audit_logs(created_at);

CREATE TABLE abuse_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    domain VARCHAR(255),
    report_type VARCHAR(50) NOT NULL CHECK (report_type IN ('domain_abuse', 'api_abuse', 'payment_fraud', 'other')),
    severity VARCHAR(50) DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    description TEXT NOT NULL,
    evidence JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(50) DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved', 'dismissed')),
    assigned_to_admin_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    resolution_notes TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX idx_abuse_reports_business_id ON abuse_reports(business_id);
CREATE INDEX idx_abuse_reports_status ON abuse_reports(status);
CREATE INDEX idx_abuse_reports_severity ON abuse_reports(severity);
CREATE INDEX idx_abuse_reports_created_at ON abuse_reports(created_at);

-- ============================================
-- Shared functions and triggers
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = TIMEZONE('utc'::text, NOW());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION generate_order_number()
RETURNS TEXT AS $$
DECLARE
    order_num TEXT;
BEGIN
    order_num := 'ORD-' || TO_CHAR(NOW(), 'YYYYMMDD') || '-' || LPAD(FLOOR(RANDOM() * 10000)::TEXT, 4, '0');
    RETURN order_num;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION prevent_subscription_field_updates()
RETURNS TRIGGER AS $$
BEGIN
    IF (NEW.plan_type IS DISTINCT FROM OLD.plan_type)
       OR (NEW.subscription_expires_at IS DISTINCT FROM OLD.subscription_expires_at) THEN
        IF auth.role() != 'service_role' THEN
            RAISE EXCEPTION 'Unauthorized: Subscription fields can only be updated by backend service';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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
CREATE TRIGGER update_team_members_updated_at BEFORE UPDATE ON team_members FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_admin_users_updated_at BEFORE UPDATE ON admin_users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_domain_restrictions_updated_at BEFORE UPDATE ON domain_restrictions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_abuse_reports_updated_at BEFORE UPDATE ON abuse_reports FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER prevent_profiles_subscription_updates
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION prevent_subscription_field_updates();

-- ============================================
-- Row Level Security
-- ============================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE businesses ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_builder_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE domain_restrictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE abuse_reports ENABLE ROW LEVEL SECURITY;

-- profiles
CREATE POLICY "Users can view their own profile"
ON profiles FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own profile"
ON profiles FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- businesses
CREATE POLICY "Users can view their own businesses"
ON businesses FOR SELECT
USING (auth.uid() = owner_id);

CREATE POLICY "Users can create their own business"
ON businesses FOR INSERT
WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Users can update their own businesses"
ON businesses FOR UPDATE
USING (auth.uid() = owner_id)
WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Users can delete their own businesses"
ON businesses FOR DELETE
USING (auth.uid() = owner_id);

-- products
CREATE POLICY "Users can view their products"
ON products FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = products.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their products"
ON products FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = products.business_id
          AND businesses.owner_id = auth.uid()
    )
);

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

CREATE POLICY "Users can delete their products"
ON products FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = products.business_id
          AND businesses.owner_id = auth.uid()
    )
);

-- customers
CREATE POLICY "Users can view their customers"
ON customers FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = customers.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their customers"
ON customers FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = customers.business_id
          AND businesses.owner_id = auth.uid()
    )
);

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

CREATE POLICY "Users can delete their customers"
ON customers FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = customers.business_id
          AND businesses.owner_id = auth.uid()
    )
);

-- conversations
CREATE POLICY "Users can view their conversations"
ON conversations FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = conversations.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their conversations"
ON conversations FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = conversations.business_id
          AND businesses.owner_id = auth.uid()
    )
);

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

CREATE POLICY "Users can delete their conversations"
ON conversations FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = conversations.business_id
          AND businesses.owner_id = auth.uid()
    )
);

-- messages
CREATE POLICY "Users can view their messages"
ON messages FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM conversations
        JOIN businesses ON businesses.id = conversations.business_id
        WHERE conversations.id = messages.conversation_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their messages"
ON messages FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1
        FROM conversations
        JOIN businesses ON businesses.id = conversations.business_id
        WHERE conversations.id = messages.conversation_id
          AND businesses.owner_id = auth.uid()
    )
);

-- orders
CREATE POLICY "Users can view their orders"
ON orders FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = orders.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their orders"
ON orders FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = orders.business_id
          AND businesses.owner_id = auth.uid()
    )
);

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

CREATE POLICY "Users can delete their orders"
ON orders FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = orders.business_id
          AND businesses.owner_id = auth.uid()
    )
);

-- payments
CREATE POLICY "Users can view their payments"
ON payments FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = payments.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their payments"
ON payments FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = payments.business_id
          AND businesses.owner_id = auth.uid()
    )
);

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

-- subscriptions
CREATE POLICY "Users can view their subscriptions"
ON subscriptions FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = subscriptions.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their subscriptions"
ON subscriptions FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = subscriptions.business_id
          AND businesses.owner_id = auth.uid()
    )
);

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

-- api keys
CREATE POLICY "Users can view their api keys"
ON api_keys FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = api_keys.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their api keys"
ON api_keys FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = api_keys.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can update their api keys"
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

CREATE POLICY "Users can delete their api keys"
ON api_keys FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = api_keys.business_id
          AND businesses.owner_id = auth.uid()
    )
);

-- webhooks
CREATE POLICY "Users can view their webhooks"
ON webhooks FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = webhooks.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their webhooks"
ON webhooks FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = webhooks.business_id
          AND businesses.owner_id = auth.uid()
    )
);

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

CREATE POLICY "Users can delete their webhooks"
ON webhooks FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = webhooks.business_id
          AND businesses.owner_id = auth.uid()
    )
);

-- logs
CREATE POLICY "Users can view their logs"
ON logs FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = logs.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their logs"
ON logs FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = logs.business_id
          AND businesses.owner_id = auth.uid()
    )
);

-- audit logs
CREATE POLICY "Users can view their audit logs"
ON audit_logs FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can create their audit logs"
ON audit_logs FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- email templates
CREATE POLICY "Users can view their email templates"
ON email_templates FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = email_templates.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can create their email templates"
ON email_templates FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = email_templates.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Users can update their email templates"
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

CREATE POLICY "Users can delete their email templates"
ON email_templates FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = email_templates.business_id
          AND businesses.owner_id = auth.uid()
    )
);

-- team members
CREATE POLICY "Owners can view their team members"
ON team_members FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Team members can view other team members"
ON team_members FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM team_members tm
        WHERE tm.business_id = team_members.business_id
          AND tm.user_id = auth.uid()
          AND tm.status = 'active'
    )
);

CREATE POLICY "Owners can create team members"
ON team_members FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Owners can update team members"
ON team_members FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
          AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "Owners can delete team members"
ON team_members FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
          AND businesses.owner_id = auth.uid()
    )
);

-- activity logs
CREATE POLICY "Team members can view activity logs"
ON activity_logs FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM team_members
        WHERE team_members.business_id = activity_logs.business_id
          AND team_members.user_id = auth.uid()
          AND team_members.status = 'active'
    )
    OR EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = activity_logs.business_id
          AND businesses.owner_id = auth.uid()
    )
);

CREATE POLICY "System can create activity logs"
ON activity_logs FOR INSERT
WITH CHECK (true);

-- Admin-only / backend-only tables:
-- RLS is enabled but no client policies are created.
-- Access is expected only through backend service_role usage.

-- ============================================
-- Grants
-- ============================================

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anon;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;

-- ============================================
-- End of consolidated setup
-- ============================================
