-- Subscription lifecycle fields and cancellation requests.
-- Safe to run repeatedly. Existing data is preserved.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS plan_type TEXT DEFAULT 'free',
    ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS subscription_start_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS subscription_end_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
    ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;

UPDATE public.profiles
SET plan_type = 'free'
WHERE plan_type IS NULL OR BTRIM(plan_type) = '';

UPDATE public.profiles
SET subscription_status = 'active'
WHERE subscription_status IS NULL OR BTRIM(subscription_status) = '';

UPDATE public.profiles
SET auto_renew = TRUE
WHERE auto_renew IS NULL;

CREATE INDEX IF NOT EXISTS profiles_subscription_end_date_idx
    ON public.profiles (subscription_end_date);
CREATE INDEX IF NOT EXISTS profiles_stripe_subscription_id_idx
    ON public.profiles (stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.refund_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    request_type TEXT NOT NULL DEFAULT 'cancellation_refund',
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    admin_notes TEXT
);

CREATE INDEX IF NOT EXISTS refund_requests_user_id_idx
    ON public.refund_requests (user_id, created_at DESC);

ALTER TABLE public.refund_requests ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.refund_requests TO service_role;

-- Keep legacy webhook/payment updates lifecycle-safe. A cancellation scheduled
-- before period end retains the paid plan until subscription_end_date.
CREATE OR REPLACE FUNCTION public.sync_profile_subscription_lifecycle()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF LOWER(COALESCE(NEW.plan_type, 'free')) = 'free'
       AND LOWER(COALESCE(OLD.plan_type, 'free')) IN ('pro', 'premium')
       AND OLD.subscription_end_date IS NOT NULL
       AND OLD.subscription_end_date > NOW()
       AND LOWER(COALESCE(NEW.subscription_status, '')) IN ('cancelled', 'canceled', 'pending_cancellation') THEN
        NEW.plan_type := OLD.plan_type;
        NEW.subscription_status := 'pending_cancellation';
        NEW.auto_renew := FALSE;
        NEW.subscription_start_date := OLD.subscription_start_date;
        NEW.subscription_end_date := OLD.subscription_end_date;
        NEW.subscription_expires_at := COALESCE(OLD.subscription_expires_at, OLD.subscription_end_date);
    ELSIF LOWER(COALESCE(NEW.plan_type, 'free')) IN ('pro', 'premium')
          AND (
              LOWER(COALESCE(OLD.plan_type, 'free')) = 'free'
              OR NEW.subscription_expires_at IS DISTINCT FROM OLD.subscription_expires_at
              OR NEW.subscription_end_date IS DISTINCT FROM OLD.subscription_end_date
          ) THEN
        NEW.subscription_start_date := NOW();
        NEW.subscription_end_date := COALESCE(NEW.subscription_end_date, NEW.subscription_expires_at, NOW() + INTERVAL '1 month');
        NEW.subscription_expires_at := NEW.subscription_end_date;
        NEW.auto_renew := COALESCE(NEW.auto_renew, TRUE);
        IF LOWER(COALESCE(NEW.subscription_status, '')) IN ('canceled', 'cancelled') THEN
            NEW.subscription_status := 'active';
        END IF;
    END IF;

    IF NEW.subscription_end_date IS NULL AND NEW.subscription_expires_at IS NOT NULL THEN
        NEW.subscription_end_date := NEW.subscription_expires_at;
    ELSIF NEW.subscription_expires_at IS NULL AND NEW.subscription_end_date IS NOT NULL THEN
        NEW.subscription_expires_at := NEW.subscription_end_date;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS profiles_subscription_lifecycle_trigger ON public.profiles;
CREATE TRIGGER profiles_subscription_lifecycle_trigger
BEFORE UPDATE ON public.profiles
FOR EACH ROW
EXECUTE FUNCTION public.sync_profile_subscription_lifecycle();

NOTIFY pgrst, 'reload schema';
