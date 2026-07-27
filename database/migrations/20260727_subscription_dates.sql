-- Subscription lifecycle fields and cancellation/refund requests.
-- Additive and safe to run repeatedly.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS plan_type TEXT DEFAULT 'free',
    ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS subscription_start_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS subscription_end_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;

ALTER TABLE public.profiles
    ALTER COLUMN plan_type SET DEFAULT 'free',
    ALTER COLUMN subscription_status SET DEFAULT 'active',
    ALTER COLUMN auto_renew SET DEFAULT TRUE;

UPDATE public.profiles
SET plan_type = 'free'
WHERE plan_type IS NULL OR BTRIM(plan_type) = '';

UPDATE public.profiles
SET subscription_status = 'active'
WHERE subscription_status IS NULL OR BTRIM(subscription_status) = '';

UPDATE public.profiles
SET auto_renew = TRUE
WHERE auto_renew IS NULL;

-- Preserve the existing expiration field while making subscription_end_date
-- the canonical lifecycle field.
UPDATE public.profiles
SET subscription_end_date = subscription_expires_at
WHERE subscription_end_date IS NULL
  AND subscription_expires_at IS NOT NULL;

UPDATE public.profiles
SET subscription_expires_at = subscription_end_date
WHERE subscription_expires_at IS NULL
  AND subscription_end_date IS NOT NULL;

-- Existing paid profiles without dates receive one current billing period.
-- The guard makes this migration idempotent and prevents extending a period
-- on repeated deployments.
UPDATE public.profiles
SET subscription_start_date = COALESCE(subscription_start_date, NOW()),
    subscription_end_date = COALESCE(subscription_end_date, NOW() + INTERVAL '1 month'),
    subscription_expires_at = COALESCE(subscription_expires_at, subscription_end_date, NOW() + INTERVAL '1 month')
WHERE LOWER(COALESCE(plan_type, 'free')) IN ('pro', 'premium')
  AND subscription_end_date IS NULL;

CREATE INDEX IF NOT EXISTS profiles_subscription_status_idx
    ON public.profiles (subscription_status);

CREATE INDEX IF NOT EXISTS profiles_stripe_subscription_id_idx
    ON public.profiles (stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.refund_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    request_type TEXT NOT NULL DEFAULT 'cancellation',
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS refund_requests_user_id_idx
    ON public.refund_requests (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS refund_requests_status_idx
    ON public.refund_requests (status);

NOTIFY pgrst, 'reload schema';
