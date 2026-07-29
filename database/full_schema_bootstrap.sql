-- ConversaPay full schema bootstrap
-- Consolidated from the repository SQL migrations.
-- Note: core business tables are owned by the existing application schema; this file
-- adds all schema objects present in this repository and is safe to run repeatedly.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE,
    email TEXT,
    full_name TEXT,
    phone TEXT,
    avatar_url TEXT,
    timezone TEXT DEFAULT 'UTC',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS id UUID;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'UTC';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS company_name TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS two_factor_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS notification_preferences JSONB NOT NULL DEFAULT '{"payment_success":true,"weekly_digest":true,"security_alerts":true,"product_updates":false}'::jsonb;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS plan_type TEXT DEFAULT 'free';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'active';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_start_date TIMESTAMPTZ;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_end_date TIMESTAMPTZ;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN DEFAULT TRUE;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;
ALTER TABLE public.profiles ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE public.profiles ALTER COLUMN timezone SET DEFAULT 'UTC';
ALTER TABLE public.profiles ALTER COLUMN updated_at SET DEFAULT NOW();
ALTER TABLE public.profiles ALTER COLUMN plan_type SET DEFAULT 'free';
ALTER TABLE public.profiles ALTER COLUMN subscription_status SET DEFAULT 'active';
ALTER TABLE public.profiles ALTER COLUMN auto_renew SET DEFAULT TRUE;
UPDATE public.profiles SET id = gen_random_uuid() WHERE id IS NULL;
UPDATE public.profiles SET timezone = 'UTC' WHERE timezone IS NULL OR BTRIM(timezone) = '';
UPDATE public.profiles SET updated_at = NOW() WHERE updated_at IS NULL;
UPDATE public.profiles SET plan_type = 'free' WHERE plan_type IS NULL OR BTRIM(plan_type) = '';
UPDATE public.profiles SET subscription_status = 'active' WHERE subscription_status IS NULL OR BTRIM(subscription_status) = '';
UPDATE public.profiles SET auto_renew = TRUE WHERE auto_renew IS NULL;
ALTER TABLE public.profiles ALTER COLUMN id SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS profiles_user_id_key ON public.profiles (user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS profiles_two_factor_enabled_idx ON public.profiles(two_factor_enabled);
CREATE INDEX IF NOT EXISTS profiles_subscription_status_idx ON public.profiles(subscription_status);
CREATE INDEX IF NOT EXISTS profiles_stripe_subscription_id_idx ON public.profiles(stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,
    event_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'received',
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    last_error TEXT,
    UNIQUE(provider, event_id)
);
CREATE INDEX IF NOT EXISTS idx_webhook_events_provider_event ON public.webhook_events(provider,event_id);
CREATE INDEX IF NOT EXISTS webhook_events_received_at_idx ON public.webhook_events(received_at DESC);
ALTER TABLE public.webhook_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.webhook_events FROM anon, authenticated;
GRANT ALL ON public.webhook_events TO service_role;

CREATE TABLE IF NOT EXISTS public.site_builder_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL,
    token_hash TEXT NOT NULL UNIQUE, expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS site_builder_tokens_user_idx ON public.site_builder_tokens(user_id, expires_at DESC);
ALTER TABLE public.site_builder_tokens ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.site_builder_tokens FROM anon, authenticated;
GRANT ALL ON public.site_builder_tokens TO service_role;

CREATE TABLE IF NOT EXISTS public.site_builder_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token_id UUID REFERENCES public.site_builder_tokens(id) ON DELETE SET NULL,
    project_name TEXT NOT NULL DEFAULT 'ConversaPay site', html TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS site_builder_projects_user_id_idx ON public.site_builder_projects(user_id);
CREATE INDEX IF NOT EXISTS site_builder_projects_updated_at_idx ON public.site_builder_projects(updated_at DESC);
ALTER TABLE public.site_builder_projects ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.site_builder_projects FROM anon, authenticated;
GRANT ALL ON public.site_builder_projects TO service_role;

CREATE OR REPLACE FUNCTION public.touch_site_builder_projects_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;
DROP TRIGGER IF EXISTS site_builder_projects_updated_at ON public.site_builder_projects;
CREATE TRIGGER site_builder_projects_updated_at BEFORE UPDATE ON public.site_builder_projects FOR EACH ROW EXECUTE FUNCTION public.touch_site_builder_projects_updated_at();

CREATE TABLE IF NOT EXISTS public.refund_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL,
    request_type TEXT NOT NULL DEFAULT 'cancellation', reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS refund_requests_user_id_idx ON public.refund_requests(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS refund_requests_status_idx ON public.refund_requests(status);

CREATE TABLE IF NOT EXISTS public.usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), business_id UUID NOT NULL, user_id UUID,
    metric TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0), source TEXT NOT NULL,
    idempotency_key TEXT, occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(business_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS usage_events_business_metric_idx ON public.usage_events(business_id, metric, occurred_at DESC);
ALTER TABLE public.usage_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.usage_events FROM anon, authenticated;
GRANT ALL ON public.usage_events TO service_role;

CREATE TABLE IF NOT EXISTS public.billing_dunning_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL, provider TEXT NOT NULL,
    provider_event_id TEXT, attempt_number INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'scheduled',
    next_attempt_at TIMESTAMPTZ, last_error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(provider, provider_event_id)
);
ALTER TABLE public.billing_dunning_attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.billing_dunning_attempts FROM anon, authenticated;
GRANT ALL ON public.billing_dunning_attempts TO service_role;

CREATE TABLE IF NOT EXISTS public.lead_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (char_length(trim(name)) BETWEEN 2 AND 120), email TEXT NOT NULL CHECK (char_length(trim(email)) BETWEEN 5 AND 320),
    company TEXT CHECK (company IS NULL OR char_length(company) <= 160), message TEXT NOT NULL CHECK (char_length(trim(message)) BETWEEN 2 AND 4000),
    source TEXT NOT NULL DEFAULT 'site-builder' CHECK (char_length(trim(source)) BETWEEN 2 AND 80), page_url TEXT CHECK (page_url IS NULL OR char_length(page_url) <= 2048),
    ip_address INET, user_agent TEXT, status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','contacted','qualified','converted','archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS lead_submissions_business_created_idx ON public.lead_submissions(business_id, created_at DESC);
CREATE INDEX IF NOT EXISTS lead_submissions_business_status_idx ON public.lead_submissions(business_id, status);
ALTER TABLE public.lead_submissions ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.site_lead_rate_limits (
    key_hash TEXT PRIMARY KEY, window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), request_count INTEGER NOT NULL DEFAULT 0 CHECK (request_count >= 0), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.site_lead_rate_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.site_lead_rate_limits FROM anon, authenticated;
GRANT ALL ON public.site_lead_rate_limits TO service_role;

CREATE OR REPLACE FUNCTION public.user_owns_business(target_business_id UUID)
RETURNS BOOLEAN LANGUAGE SQL STABLE SECURITY DEFINER SET search_path = public AS $$
SELECT EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = target_business_id AND b.owner_id = auth.uid());
$$;
REVOKE ALL ON FUNCTION public.user_owns_business(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.user_owns_business(UUID) TO authenticated;

CREATE OR REPLACE FUNCTION public.mark_email_verified(p_user_id UUID)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_verified BOOLEAN;
BEGIN
 UPDATE public.profiles SET email_verified = TRUE, email_verification_token = NULL, email_verification_expires_at = NULL WHERE user_id = p_user_id RETURNING email_verified INTO v_verified;
 RETURN COALESCE(v_verified, FALSE);
END; $$;
GRANT EXECUTE ON FUNCTION public.mark_email_verified(UUID) TO anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.claim_webhook_event(p_provider TEXT, p_event_id TEXT, p_event_type TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE claimed BOOLEAN := FALSE;
BEGIN
 INSERT INTO public.webhook_events(provider,event_id,status,received_at) VALUES(p_provider,p_event_id,'processing',NOW()) ON CONFLICT(provider,event_id) DO NOTHING;
 IF FOUND THEN RETURN TRUE; END IF;
 UPDATE public.webhook_events SET status='processing', received_at=NOW() WHERE provider=p_provider AND event_id=p_event_id AND status IN ('failed','received');
 GET DIAGNOSTICS claimed = ROW_COUNT; RETURN claimed;
END; $$;
REVOKE ALL ON FUNCTION public.claim_webhook_event(TEXT,TEXT,TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_webhook_event(TEXT,TEXT,TEXT) TO service_role;

CREATE OR REPLACE FUNCTION public.touch_lead_submissions_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;
DROP TRIGGER IF EXISTS lead_submissions_touch_updated_at ON public.lead_submissions;
CREATE TRIGGER lead_submissions_touch_updated_at BEFORE UPDATE ON public.lead_submissions FOR EACH ROW EXECUTE FUNCTION public.touch_lead_submissions_updated_at();

CREATE OR REPLACE FUNCTION public.consume_site_lead_rate_limit(p_key TEXT, p_limit INTEGER DEFAULT 5, p_window_seconds INTEGER DEFAULT 3600)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE current_row public.site_lead_rate_limits%ROWTYPE; now_value TIMESTAMPTZ := NOW();
BEGIN
 IF p_key IS NULL OR length(trim(p_key)) < 16 OR p_limit < 1 OR p_window_seconds < 1 THEN RETURN FALSE; END IF;
 PERFORM pg_advisory_xact_lock(hashtext(p_key));
 SELECT * INTO current_row FROM public.site_lead_rate_limits WHERE key_hash=p_key FOR UPDATE;
 IF NOT FOUND OR current_row.window_started_at + make_interval(secs=>p_window_seconds) <= now_value THEN
  INSERT INTO public.site_lead_rate_limits(key_hash,window_started_at,request_count,updated_at) VALUES(p_key,now_value,1,now_value)
  ON CONFLICT(key_hash) DO UPDATE SET window_started_at=excluded.window_started_at,request_count=1,updated_at=excluded.updated_at; RETURN TRUE;
 END IF;
 IF current_row.request_count >= p_limit THEN RETURN FALSE; END IF;
 UPDATE public.site_lead_rate_limits SET request_count=request_count+1,updated_at=now_value WHERE key_hash=p_key; RETURN TRUE;
END; $$;
REVOKE ALL ON FUNCTION public.consume_site_lead_rate_limit(TEXT,INTEGER,INTEGER) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.consume_site_lead_rate_limit(TEXT,INTEGER,INTEGER) TO service_role;

DO $$ BEGIN
 IF to_regclass('public.admin_users') IS NOT NULL THEN
  ALTER TABLE public.admin_users ADD COLUMN IF NOT EXISTS username TEXT;
  CREATE UNIQUE INDEX IF NOT EXISTS admin_users_username_lower_key ON public.admin_users (LOWER(username)) WHERE username IS NOT NULL;
 END IF;
 IF to_regclass('public.businesses') IS NOT NULL THEN
  ALTER TABLE public.businesses DROP CONSTRAINT IF EXISTS businesses_subscription_tier_check;
  ALTER TABLE public.businesses ADD CONSTRAINT businesses_subscription_tier_check CHECK (subscription_tier IN ('free','pro','premium'));
 END IF;
END $$;

DO $$ BEGIN
 IF to_regclass('public.businesses') IS NOT NULL THEN ALTER TABLE public.businesses ENABLE ROW LEVEL SECURITY; END IF;
 IF to_regclass('public.products') IS NOT NULL THEN ALTER TABLE public.products ENABLE ROW LEVEL SECURITY; END IF;
 IF to_regclass('public.orders') IS NOT NULL THEN ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY; END IF;
 IF to_regclass('public.payments') IS NOT NULL THEN ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY; END IF;
 IF to_regclass('public.api_keys') IS NOT NULL THEN ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY; END IF;
 IF to_regclass('public.webhooks') IS NOT NULL THEN ALTER TABLE public.webhooks ENABLE ROW LEVEL SECURITY; END IF;
END $$;

DO $$ BEGIN
 IF to_regclass('public.businesses') IS NOT NULL THEN
  DROP POLICY IF EXISTS businesses_owner_isolation ON public.businesses;
  CREATE POLICY businesses_owner_isolation ON public.businesses FOR ALL TO authenticated USING (owner_id=auth.uid()) WITH CHECK (owner_id=auth.uid());
 END IF;
 IF to_regclass('public.products') IS NOT NULL THEN
  DROP POLICY IF EXISTS products_business_isolation ON public.products;
  CREATE POLICY products_business_isolation ON public.products FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id));
 END IF;
 IF to_regclass('public.orders') IS NOT NULL THEN
  DROP POLICY IF EXISTS orders_business_isolation ON public.orders;
  CREATE POLICY orders_business_isolation ON public.orders FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id));
 END IF;
 IF to_regclass('public.api_keys') IS NOT NULL THEN
  DROP POLICY IF EXISTS api_keys_business_isolation ON public.api_keys;
  CREATE POLICY api_keys_business_isolation ON public.api_keys FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id));
 END IF;
 IF to_regclass('public.webhooks') IS NOT NULL THEN
  DROP POLICY IF EXISTS webhooks_business_isolation ON public.webhooks;
  CREATE POLICY webhooks_business_isolation ON public.webhooks FOR ALL TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id));
 END IF;
 IF to_regclass('public.lead_submissions') IS NOT NULL THEN
  DROP POLICY IF EXISTS lead_submissions_owner_select ON public.lead_submissions;
  DROP POLICY IF EXISTS lead_submissions_owner_update ON public.lead_submissions;
  DROP POLICY IF EXISTS lead_submissions_owner_delete ON public.lead_submissions;
  CREATE POLICY lead_submissions_owner_select ON public.lead_submissions FOR SELECT TO authenticated USING (public.user_owns_business(business_id));
  CREATE POLICY lead_submissions_owner_update ON public.lead_submissions FOR UPDATE TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id));
  CREATE POLICY lead_submissions_owner_delete ON public.lead_submissions FOR DELETE TO authenticated USING (public.user_owns_business(business_id));
 END IF;
 IF to_regclass('public.payments') IS NOT NULL THEN
  DROP POLICY IF EXISTS payments_owner_read ON public.payments;
  DROP POLICY IF EXISTS payments_service_all ON public.payments;
  CREATE POLICY payments_owner_read ON public.payments FOR SELECT TO authenticated USING (public.user_owns_business(business_id));
  REVOKE ALL ON public.payments FROM anon;
  GRANT ALL ON public.payments TO service_role;
 END IF;
END $$;

DO $$ DECLARE target_table TEXT; BEGIN
 FOREACH target_table IN ARRAY ARRAY['businesses','products','orders','payments','api_keys','webhooks'] LOOP
  IF to_regclass('public.'||target_table) IS NOT NULL THEN EXECUTE format('REVOKE ALL ON public.%I FROM anon',target_table); END IF;
 END LOOP;
END $$;

UPDATE public.profiles SET subscription_end_date=subscription_expires_at WHERE subscription_end_date IS NULL AND subscription_expires_at IS NOT NULL;
UPDATE public.profiles SET subscription_expires_at=subscription_end_date WHERE subscription_expires_at IS NULL AND subscription_end_date IS NOT NULL;
UPDATE public.profiles SET subscription_start_date=COALESCE(subscription_start_date,NOW()), subscription_end_date=COALESCE(subscription_end_date,NOW()+INTERVAL '1 month'), subscription_expires_at=COALESCE(subscription_expires_at,subscription_end_date,NOW()+INTERVAL '1 month') WHERE LOWER(COALESCE(plan_type,'free')) IN ('pro','premium') AND subscription_end_date IS NULL;
NOTIFY pgrst, 'reload schema';
