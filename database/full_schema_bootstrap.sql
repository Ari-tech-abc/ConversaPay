-- ConversaPay full schema bootstrap
-- Idempotent bootstrap for the complete application schema.
-- Existing data is preserved; core tables are created when absent and extended when present.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Profiles and account state
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE,
    email TEXT,
    full_name TEXT,
    phone TEXT,
    company_name TEXT,
    avatar_url TEXT,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    role TEXT NOT NULL DEFAULT 'user',
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verification_token TEXT,
    email_verification_expires_at TIMESTAMPTZ,
    plan_type TEXT NOT NULL DEFAULT 'free',
    subscription_status TEXT NOT NULL DEFAULT 'active',
    subscription_start_date TIMESTAMPTZ,
    subscription_end_date TIMESTAMPTZ,
    subscription_expires_at TIMESTAMPTZ,
    auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    whatsapp_phone_number_id TEXT,
    whatsapp_access_token TEXT,
    whatsapp_verify_token TEXT,
    two_factor_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    notification_preferences JSONB NOT NULL DEFAULT '{"payment_success":true,"weekly_digest":true,"security_alerts":true,"product_updates":false}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS id UUID;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS company_name TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'UTC';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS email_verification_token TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMPTZ;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS plan_type TEXT DEFAULT 'free';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'active';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_start_date TIMESTAMPTZ;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_end_date TIMESTAMPTZ;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN DEFAULT TRUE;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS whatsapp_phone_number_id TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS whatsapp_access_token TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS whatsapp_verify_token TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS two_factor_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS notification_preferences JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
UPDATE public.profiles SET id = gen_random_uuid() WHERE id IS NULL;
UPDATE public.profiles SET timezone = 'UTC' WHERE timezone IS NULL OR BTRIM(timezone) = '';
UPDATE public.profiles SET role = 'user' WHERE role IS NULL OR BTRIM(role) = '';
UPDATE public.profiles SET plan_type = 'free' WHERE plan_type IS NULL OR BTRIM(plan_type) = '';
UPDATE public.profiles SET subscription_status = 'active' WHERE subscription_status IS NULL OR BTRIM(subscription_status) = '';
UPDATE public.profiles SET auto_renew = TRUE WHERE auto_renew IS NULL;
UPDATE public.profiles SET email_verified = FALSE WHERE email_verified IS NULL;
UPDATE public.profiles SET two_factor_enabled = FALSE WHERE two_factor_enabled IS NULL;
UPDATE public.profiles SET notification_preferences = '{"payment_success":true,"weekly_digest":true,"security_alerts":true,"product_updates":false}'::jsonb WHERE notification_preferences IS NULL;
UPDATE public.profiles SET created_at = NOW() WHERE created_at IS NULL;
UPDATE public.profiles SET updated_at = NOW() WHERE updated_at IS NULL;
ALTER TABLE public.profiles ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE public.profiles ALTER COLUMN id SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS profiles_user_id_key ON public.profiles(user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS profiles_stripe_customer_id_key ON public.profiles(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS profiles_subscription_status_idx ON public.profiles(subscription_status);
CREATE INDEX IF NOT EXISTS profiles_stripe_subscription_id_idx ON public.profiles(stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS profiles_whatsapp_verify_token_idx ON public.profiles(whatsapp_verify_token) WHERE whatsapp_verify_token IS NOT NULL;

-- Tenant and catalog tables
CREATE TABLE IF NOT EXISTS public.businesses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id TEXT NOT NULL UNIQUE,
    business_name TEXT NOT NULL,
    description TEXT,
    owner_id UUID NOT NULL,
    subscription_tier TEXT NOT NULL DEFAULT 'free',
    subscription_status TEXT NOT NULL DEFAULT 'active',
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS business_id TEXT;
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS business_name TEXT;
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS owner_id UUID;
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'free';
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'active';
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
CREATE UNIQUE INDEX IF NOT EXISTS businesses_business_id_key ON public.businesses(business_id);
CREATE INDEX IF NOT EXISTS businesses_owner_id_idx ON public.businesses(owner_id);
CREATE INDEX IF NOT EXISTS businesses_active_idx ON public.businesses(is_active);

CREATE TABLE IF NOT EXISTS public.products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    price NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (price >= 0),
    currency TEXT NOT NULL DEFAULT 'ILS',
    image_url TEXT,
    payment_link TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    inventory_count INTEGER NOT NULL DEFAULT -1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(business_id, item_key)
);
CREATE INDEX IF NOT EXISTS products_business_active_idx ON public.products(business_id,is_active);

CREATE TABLE IF NOT EXISTS public.customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    email TEXT,
    phone TEXT,
    name TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    total_purchases NUMERIC(12,2) NOT NULL DEFAULT 0,
    purchase_count INTEGER NOT NULL DEFAULT 0,
    last_purchase_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS customers_business_idx ON public.customers(business_id);
CREATE INDEX IF NOT EXISTS customers_email_idx ON public.customers(business_id,email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS customers_phone_idx ON public.customers(business_id,phone) WHERE phone IS NOT NULL;

-- Conversations and chat history
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES public.customers(id) ON DELETE SET NULL,
    session_id TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'web',
    status TEXT NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(business_id, session_id)
);
CREATE INDEX IF NOT EXISTS conversations_business_started_idx ON public.conversations(business_id,started_at DESC);
CREATE INDEX IF NOT EXISTS conversations_session_idx ON public.conversations(session_id);

CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    intent TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS messages_conversation_created_idx ON public.messages(conversation_id,created_at);

-- Orders, payments and integrations
CREATE TABLE IF NOT EXISTS public.orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES public.customers(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES public.conversations(id) ON DELETE SET NULL,
    order_number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    payment_status TEXT NOT NULL DEFAULT 'pending',
    subtotal NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax NUMERIC(12,2) NOT NULL DEFAULT 0,
    total NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'ILS',
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    customer_info JSONB NOT NULL DEFAULT '{}'::jsonb,
    shipping_address JSONB,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS orders_business_created_idx ON public.orders(business_id,created_at DESC);
CREATE INDEX IF NOT EXISTS orders_business_status_idx ON public.orders(business_id,status);
CREATE INDEX IF NOT EXISTS orders_customer_idx ON public.orders(customer_id);

CREATE TABLE IF NOT EXISTS public.payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    order_id UUID REFERENCES public.orders(id) ON DELETE SET NULL,
    amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'ILS',
    status TEXT NOT NULL DEFAULT 'pending',
    payment_method TEXT,
    customer_email TEXT,
    customer_name TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS payments_business_created_idx ON public.payments(business_id,created_at DESC);
CREATE INDEX IF NOT EXISTS payments_order_idx ON public.payments(order_id);
CREATE INDEX IF NOT EXISTS payments_status_idx ON public.payments(status);

CREATE TABLE IF NOT EXISTS public.api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    permissions JSONB NOT NULL DEFAULT '["read"]'::jsonb,
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS api_keys_business_active_idx ON public.api_keys(business_id,is_active);

CREATE TABLE IF NOT EXISTS public.webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    events JSONB NOT NULL DEFAULT '[]'::jsonb,
    secret TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_triggered_at TIMESTAMPTZ,
    failure_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS webhooks_business_active_idx ON public.webhooks(business_id,is_active);

-- Observability and usage
CREATE TABLE IF NOT EXISTS public.logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID REFERENCES public.businesses(id) ON DELETE SET NULL,
    level TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS logs_business_created_idx ON public.logs(business_id,created_at DESC);
CREATE INDEX IF NOT EXISTS logs_level_created_idx ON public.logs(level,created_at DESC);

CREATE TABLE IF NOT EXISTS public.usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    business_id UUID REFERENCES public.businesses(id) ON DELETE SET NULL,
    action TEXT,
    metric TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS usage_logs_user_created_idx ON public.usage_logs(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS usage_logs_business_created_idx ON public.usage_logs(business_id,created_at DESC);

CREATE TABLE IF NOT EXISTS public.usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), business_id UUID NOT NULL, user_id UUID,
    metric TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0), source TEXT NOT NULL,
    idempotency_key TEXT, occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(business_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS usage_events_business_metric_idx ON public.usage_events(business_id,metric,occurred_at DESC);

-- Admin, abuse and billing support
CREATE TABLE IF NOT EXISTS public.admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), username TEXT UNIQUE, email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'admin', status TEXT NOT NULL DEFAULT 'active',
    login_attempts INTEGER NOT NULL DEFAULT 0, locked_until TIMESTAMPTZ, last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.admin_users ADD COLUMN IF NOT EXISTS username TEXT;
ALTER TABLE public.admin_users ADD COLUMN IF NOT EXISTS login_attempts INTEGER DEFAULT 0;
ALTER TABLE public.admin_users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;
ALTER TABLE public.admin_users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;
ALTER TABLE public.admin_users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
CREATE UNIQUE INDEX IF NOT EXISTS admin_users_username_lower_key ON public.admin_users(LOWER(username)) WHERE username IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), admin_id UUID REFERENCES public.admin_users(id) ON DELETE SET NULL,
    action TEXT NOT NULL, resource_type TEXT, resource_id TEXT, business_id UUID,
    details JSONB NOT NULL DEFAULT '{}'::jsonb, ip_address INET, user_agent TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS admin_audit_logs_created_idx ON public.admin_audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS admin_audit_logs_admin_idx ON public.admin_audit_logs(admin_id,created_at DESC);

CREATE TABLE IF NOT EXISTS public.domain_restrictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    domain TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', reason_for_status TEXT,
    max_domains_allowed INTEGER NOT NULL DEFAULT 1, monthly_api_calls_limit INTEGER NOT NULL DEFAULT 100000,
    monthly_reset_date DATE, blocked_at TIMESTAMPTZ, blocked_by_admin_id UUID REFERENCES public.admin_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS domain_restrictions_business_idx ON public.domain_restrictions(business_id);
CREATE INDEX IF NOT EXISTS domain_restrictions_status_idx ON public.domain_restrictions(status);

CREATE TABLE IF NOT EXISTS public.abuse_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    domain TEXT, report_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'medium', description TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb, status TEXT NOT NULL DEFAULT 'open', assigned_to_admin_id UUID REFERENCES public.admin_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS abuse_reports_status_idx ON public.abuse_reports(status,severity);
CREATE INDEX IF NOT EXISTS abuse_reports_business_idx ON public.abuse_reports(business_id);

CREATE TABLE IF NOT EXISTS public.refund_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL, request_type TEXT NOT NULL DEFAULT 'cancellation',
    reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS refund_requests_user_idx ON public.refund_requests(user_id,created_at DESC);

CREATE TABLE IF NOT EXISTS public.billing_dunning_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL, provider TEXT NOT NULL, provider_event_id TEXT,
    attempt_number INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'scheduled', next_attempt_at TIMESTAMPTZ,
    last_error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(provider,provider_event_id)
);

-- Webhook replay protection and site-builder storage
CREATE TABLE IF NOT EXISTS public.webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), provider TEXT NOT NULL, event_id TEXT NOT NULL,
    event_type TEXT, status TEXT NOT NULL DEFAULT 'received', received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), processed_at TIMESTAMPTZ, last_error TEXT,
    UNIQUE(provider,event_id)
);
CREATE INDEX IF NOT EXISTS webhook_events_received_idx ON public.webhook_events(received_at DESC);
CREATE TABLE IF NOT EXISTS public.site_builder_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL, token_hash TEXT NOT NULL UNIQUE, expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS site_builder_tokens_user_idx ON public.site_builder_tokens(user_id,expires_at DESC);
CREATE TABLE IF NOT EXISTS public.site_builder_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token_id UUID REFERENCES public.site_builder_tokens(id) ON DELETE SET NULL, project_name TEXT NOT NULL DEFAULT 'ConversaPay site', html TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS site_builder_projects_user_idx ON public.site_builder_projects(user_id,created_at DESC);
CREATE TABLE IF NOT EXISTS public.lead_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    name TEXT NOT NULL, email TEXT NOT NULL, company TEXT, message TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'site-builder', page_url TEXT,
    ip_address INET, user_agent TEXT, status TEXT NOT NULL DEFAULT 'new', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS lead_submissions_business_created_idx ON public.lead_submissions(business_id,created_at DESC);
CREATE TABLE IF NOT EXISTS public.site_lead_rate_limits (
    key_hash TEXT PRIMARY KEY, window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), request_count INTEGER NOT NULL DEFAULT 0, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Functions used by the application
CREATE OR REPLACE FUNCTION public.user_owns_business(target_business_id UUID)
RETURNS BOOLEAN LANGUAGE SQL STABLE SECURITY DEFINER SET search_path=public AS $$
    SELECT EXISTS(SELECT 1 FROM public.businesses b WHERE b.id=target_business_id AND b.owner_id=auth.uid());
$$;
REVOKE ALL ON FUNCTION public.user_owns_business(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.user_owns_business(UUID) TO authenticated;

CREATE OR REPLACE FUNCTION public.mark_email_verified(p_user_id UUID)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE v_verified BOOLEAN;
BEGIN
    UPDATE public.profiles SET email_verified=TRUE,email_verification_token=NULL,email_verification_expires_at=NULL WHERE user_id=p_user_id RETURNING email_verified INTO v_verified;
    RETURN COALESCE(v_verified,FALSE);
END; $$;
GRANT EXECUTE ON FUNCTION public.mark_email_verified(UUID) TO anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.claim_webhook_event(p_provider TEXT,p_event_id TEXT,p_event_type TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE claimed BOOLEAN:=FALSE;
BEGIN
    INSERT INTO public.webhook_events(provider,event_id,event_type,status,received_at) VALUES(p_provider,p_event_id,p_event_type,'processing',NOW()) ON CONFLICT(provider,event_id) DO NOTHING;
    IF FOUND THEN RETURN TRUE; END IF;
    UPDATE public.webhook_events SET status='processing',received_at=NOW(),event_type=COALESCE(p_event_type,event_type) WHERE provider=p_provider AND event_id=p_event_id AND status IN ('failed','received');
    GET DIAGNOSTICS claimed=ROW_COUNT;
    RETURN claimed;
END; $$;
REVOKE ALL ON FUNCTION public.claim_webhook_event(TEXT,TEXT,TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_webhook_event(TEXT,TEXT,TEXT) TO service_role;

CREATE OR REPLACE FUNCTION public.consume_site_lead_rate_limit(p_key TEXT,p_limit INTEGER DEFAULT 5,p_window_seconds INTEGER DEFAULT 3600)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE current_row public.site_lead_rate_limits%ROWTYPE; now_value TIMESTAMPTZ:=NOW();
BEGIN
    IF p_key IS NULL OR length(trim(p_key))<16 OR p_limit<1 OR p_window_seconds<1 THEN RETURN FALSE; END IF;
    PERFORM pg_advisory_xact_lock(hashtext(p_key));
    SELECT * INTO current_row FROM public.site_lead_rate_limits WHERE key_hash=p_key FOR UPDATE;
    IF NOT FOUND OR current_row.window_started_at+make_interval(secs=>p_window_seconds)<=now_value THEN
        INSERT INTO public.site_lead_rate_limits(key_hash,window_started_at,request_count,updated_at) VALUES(p_key,now_value,1,now_value)
        ON CONFLICT(key_hash) DO UPDATE SET window_started_at=EXCLUDED.window_started_at,request_count=1,updated_at=EXCLUDED.updated_at;
        RETURN TRUE;
    END IF;
    IF current_row.request_count>=p_limit THEN RETURN FALSE; END IF;
    UPDATE public.site_lead_rate_limits SET request_count=request_count+1,updated_at=now_value WHERE key_hash=p_key;
    RETURN TRUE;
END; $$;
REVOKE ALL ON FUNCTION public.consume_site_lead_rate_limit(TEXT,INTEGER,INTEGER) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.consume_site_lead_rate_limit(TEXT,INTEGER,INTEGER) TO service_role;

CREATE OR REPLACE FUNCTION public.touch_site_builder_projects_updated_at() RETURNS TRIGGER LANGUAGE plpgsql SET search_path=public AS $$ BEGIN NEW.updated_at=NOW(); RETURN NEW; END; $$;
DROP TRIGGER IF EXISTS site_builder_projects_updated_at ON public.site_builder_projects;
CREATE TRIGGER site_builder_projects_updated_at BEFORE UPDATE ON public.site_builder_projects FOR EACH ROW EXECUTE FUNCTION public.touch_site_builder_projects_updated_at();

-- Constraints, RLS and grants are conditional so the bootstrap also works against legacy databases.
DO $$
DECLARE t TEXT;
BEGIN
    IF to_regclass('public.businesses') IS NOT NULL THEN
        ALTER TABLE public.businesses ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS businesses_owner_isolation ON public.businesses';
        EXECUTE 'CREATE POLICY businesses_owner_isolation ON public.businesses FOR ALL TO authenticated USING (owner_id=auth.uid()) WITH CHECK (owner_id=auth.uid())';
    END IF;
    IF to_regclass('public.products') IS NOT NULL THEN
        ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS products_business_isolation ON public.products';
        EXECUTE 'CREATE POLICY products_business_isolation ON public.products FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id))';
    END IF;
    IF to_regclass('public.customers') IS NOT NULL THEN
        ALTER TABLE public.customers ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS customers_business_isolation ON public.customers';
        EXECUTE 'CREATE POLICY customers_business_isolation ON public.customers FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id))';
    END IF;
    IF to_regclass('public.conversations') IS NOT NULL THEN
        ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS conversations_business_isolation ON public.conversations';
        EXECUTE 'CREATE POLICY conversations_business_isolation ON public.conversations FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id))';
    END IF;
    IF to_regclass('public.orders') IS NOT NULL THEN
        ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS orders_business_isolation ON public.orders';
        EXECUTE 'CREATE POLICY orders_business_isolation ON public.orders FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id))';
    END IF;
    IF to_regclass('public.payments') IS NOT NULL THEN
        ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS payments_owner_read ON public.payments';
        EXECUTE 'CREATE POLICY payments_owner_read ON public.payments FOR SELECT TO authenticated USING (public.user_owns_business(business_id))';
        REVOKE ALL ON public.payments FROM anon;
        GRANT ALL ON public.payments TO service_role;
    END IF;
    IF to_regclass('public.api_keys') IS NOT NULL THEN
        ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS api_keys_business_isolation ON public.api_keys';
        EXECUTE 'CREATE POLICY api_keys_business_isolation ON public.api_keys FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id))';
    END IF;
    IF to_regclass('public.webhooks') IS NOT NULL THEN
        ALTER TABLE public.webhooks ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS webhooks_business_isolation ON public.webhooks';
        EXECUTE 'CREATE POLICY webhooks_business_isolation ON public.webhooks FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id))';
    END IF;
    IF to_regclass('public.logs') IS NOT NULL THEN
        ALTER TABLE public.logs ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS logs_business_isolation ON public.logs';
        EXECUTE 'CREATE POLICY logs_business_isolation ON public.logs FOR ALL TO authenticated USING (business_id IS NULL OR public.user_owns_business(business_id)) WITH CHECK (business_id IS NULL OR public.user_owns_business(business_id))';
    END IF;
    IF to_regclass('public.lead_submissions') IS NOT NULL THEN
        ALTER TABLE public.lead_submissions ENABLE ROW LEVEL SECURITY;
        EXECUTE 'DROP POLICY IF EXISTS lead_submissions_owner_select ON public.lead_submissions';
        EXECUTE 'DROP POLICY IF EXISTS lead_submissions_owner_update ON public.lead_submissions';
        EXECUTE 'DROP POLICY IF EXISTS lead_submissions_owner_delete ON public.lead_submissions';
        EXECUTE 'CREATE POLICY lead_submissions_owner_select ON public.lead_submissions FOR SELECT TO authenticated USING (public.user_owns_business(business_id))';
        EXECUTE 'CREATE POLICY lead_submissions_owner_update ON public.lead_submissions FOR UPDATE TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id))';
        EXECUTE 'CREATE POLICY lead_submissions_owner_delete ON public.lead_submissions FOR DELETE TO authenticated USING (public.user_owns_business(business_id))';
    END IF;
    FOREACH t IN ARRAY ARRAY['webhook_events','site_builder_tokens','site_builder_projects','usage_events','billing_dunning_attempts','site_lead_rate_limits'] LOOP
        IF to_regclass('public.'||t) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
            EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated',t);
            EXECUTE format('GRANT ALL ON public.%I TO service_role',t);
        END IF;
    END LOOP;
END $$;

DO $$ BEGIN
    IF to_regclass('public.businesses') IS NOT NULL THEN
        ALTER TABLE public.businesses DROP CONSTRAINT IF EXISTS businesses_subscription_tier_check;
        ALTER TABLE public.businesses ADD CONSTRAINT businesses_subscription_tier_check CHECK (subscription_tier IN ('free','pro','premium'));
    END IF;
END $$;

NOTIFY pgrst,'reload schema';
