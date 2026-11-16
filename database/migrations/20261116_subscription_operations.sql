-- Platform subscriptions. Additive, service-role-only writes; no card data.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_provider TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS provider_subscription_id TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS provider_customer_id TEXT;

CREATE TABLE IF NOT EXISTS public.subscription_checkout_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(user_id),
    provider TEXT NOT NULL CHECK (provider IN ('stripe','isracard')),
    plan_type TEXT NOT NULL CHECK (plan_type IN ('pro','premium')),
    status TEXT NOT NULL DEFAULT 'creating' CHECK (status IN ('creating','open','completed','expired')),
    provider_session_id TEXT,
    checkout_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS subscription_checkout_one_pending
    ON public.subscription_checkout_attempts(user_id) WHERE status IN ('creating','open');
CREATE UNIQUE INDEX IF NOT EXISTS subscription_checkout_session
    ON public.subscription_checkout_attempts(provider,provider_session_id) WHERE provider_session_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.subscription_cancellations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(user_id),
    provider TEXT NOT NULL CHECK (provider IN ('stripe','isracard')),
    provider_subscription_id TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 3 AND 4000),
    request_refund BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','confirmed')),
    refund_request_id UUID REFERENCES public.refund_requests(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id,provider,provider_subscription_id)
);
ALTER TABLE public.subscription_checkout_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscription_cancellations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.subscription_checkout_attempts,public.subscription_cancellations FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.subscription_checkout_attempts,public.subscription_cancellations TO service_role;

CREATE OR REPLACE FUNCTION public.claim_subscription_checkout(p_user_id UUID,p_provider TEXT,p_plan TEXT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE profile public.profiles%ROWTYPE; attempt public.subscription_checkout_attempts%ROWTYPE;
BEGIN
    IF p_provider NOT IN ('stripe','isracard') OR p_plan NOT IN ('pro','premium') THEN RAISE EXCEPTION 'invalid billing request'; END IF;
    SELECT * INTO profile FROM public.profiles WHERE user_id=p_user_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('error','billing_profile_missing'); END IF;
    IF (coalesce(profile.provider_subscription_id,profile.stripe_subscription_id) IS NOT NULL
            AND profile.subscription_status NOT IN ('canceled','incomplete_expired'))
       OR (profile.plan_type IN ('pro','premium') AND coalesce(profile.subscription_expires_at,profile.subscription_end_date)>now()) THEN
        RETURN jsonb_build_object('error','billing_subscription_exists');
    END IF;
    SELECT * INTO attempt FROM public.subscription_checkout_attempts
      WHERE user_id=p_user_id AND status IN ('creating','open') FOR UPDATE;
    IF FOUND THEN RETURN to_jsonb(attempt); END IF;
    INSERT INTO public.subscription_checkout_attempts(user_id,provider,plan_type)
      VALUES(p_user_id,p_provider,p_plan) RETURNING * INTO attempt;
    RETURN to_jsonb(attempt);
END;
$$;

CREATE OR REPLACE FUNCTION public.finish_subscription_checkout(p_id UUID,p_user_id UUID,p_session_id TEXT,p_url TEXT,p_status TEXT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE attempt public.subscription_checkout_attempts%ROWTYPE;
BEGIN
    SELECT * INTO attempt FROM public.subscription_checkout_attempts WHERE id=p_id AND user_id=p_user_id FOR UPDATE;
    IF NOT FOUND OR p_status NOT IN ('open','expired') OR nullif(p_session_id,'') IS NULL
       OR (attempt.provider_session_id IS NOT NULL AND attempt.provider_session_id<>p_session_id) THEN
        RETURN jsonb_build_object('error','billing_session_mismatch');
    END IF;
    IF attempt.status='completed' THEN RETURN jsonb_build_object('error','billing_confirmation_pending'); END IF;
    IF attempt.status='expired' AND p_status<>'expired' THEN RETURN jsonb_build_object('error','billing_checkout_expired'); END IF;
    IF p_status='expired' AND attempt.provider_session_id IS NULL THEN RETURN jsonb_build_object('error','billing_session_mismatch'); END IF;
    IF p_status='open' AND (p_url IS NULL OR p_url NOT LIKE 'https://%') THEN RAISE EXCEPTION 'invalid checkout URL'; END IF;
    UPDATE public.subscription_checkout_attempts SET status=p_status,provider_session_id=p_session_id,
      checkout_url=CASE WHEN p_status='open' THEN p_url ELSE checkout_url END,updated_at=now()
      WHERE id=p_id RETURNING * INTO attempt;
    RETURN to_jsonb(attempt);
END;
$$;

CREATE OR REPLACE FUNCTION public.request_subscription_cancellation(p_user_id UUID,p_provider TEXT,p_subscription_id TEXT,p_reason TEXT,p_refund BOOLEAN)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE profile public.profiles%ROWTYPE; cancellation public.subscription_cancellations%ROWTYPE;
BEGIN
    SELECT * INTO profile FROM public.profiles WHERE user_id=p_user_id FOR UPDATE;
    IF NOT FOUND OR p_subscription_id IS DISTINCT FROM coalesce(profile.provider_subscription_id,profile.stripe_subscription_id)
       OR p_provider IS DISTINCT FROM coalesce(profile.subscription_provider,'stripe') THEN
        RETURN jsonb_build_object('error','billing_subscription_mismatch');
    END IF;
    INSERT INTO public.subscription_cancellations(user_id,provider,provider_subscription_id,reason,request_refund)
      VALUES(p_user_id,p_provider,p_subscription_id,p_reason,p_refund)
      ON CONFLICT(user_id,provider,provider_subscription_id) DO UPDATE
      SET request_refund=public.subscription_cancellations.request_refund OR excluded.request_refund,updated_at=now()
      RETURNING * INTO cancellation;
    RETURN to_jsonb(cancellation);
END;
$$;

CREATE OR REPLACE FUNCTION public.confirm_subscription_cancellation(p_id UUID,p_user_id UUID,p_subscription_id TEXT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE cancellation public.subscription_cancellations%ROWTYPE; profile public.profiles%ROWTYPE; refund_id UUID;
BEGIN
    -- Use the same profile-first lock order as all other subscription operations.
    SELECT * INTO profile FROM public.profiles WHERE user_id=p_user_id FOR UPDATE;
    SELECT * INTO cancellation FROM public.subscription_cancellations WHERE id=p_id AND user_id=p_user_id FOR UPDATE;
    IF NOT FOUND OR cancellation.provider_subscription_id IS DISTINCT FROM p_subscription_id
       OR p_subscription_id IS DISTINCT FROM coalesce(profile.provider_subscription_id,profile.stripe_subscription_id) THEN
        RETURN jsonb_build_object('error','billing_subscription_mismatch');
    END IF;
    UPDATE public.profiles SET auto_renew=false,
      subscription_status=CASE WHEN subscription_status='canceled' THEN 'canceled' ELSE 'pending_cancellation' END,
      updated_at=now() WHERE user_id=p_user_id;
    UPDATE public.businesses SET subscription_status='pending_cancellation' WHERE owner_id=p_user_id AND subscription_tier IN ('pro','premium');
    refund_id=cancellation.refund_request_id;
    IF cancellation.request_refund AND refund_id IS NULL THEN
        INSERT INTO public.refund_requests(user_id,request_type,reason,status)
          VALUES(p_user_id,'refund_and_cancellation',cancellation.reason,'pending') RETURNING id INTO refund_id;
    END IF;
    UPDATE public.subscription_cancellations SET status='confirmed',confirmed_at=coalesce(confirmed_at,now()),refund_request_id=refund_id,updated_at=now()
      WHERE id=p_id RETURNING * INTO cancellation;
    RETURN to_jsonb(cancellation);
END;
$$;

CREATE OR REPLACE FUNCTION public.apply_subscription_snapshot(
    p_user_id UUID,p_provider TEXT,p_subscription_id TEXT,p_customer_id TEXT,p_plan TEXT,p_status TEXT,
    p_period_start TIMESTAMPTZ,p_period_end TIMESTAMPTZ,p_cancel_at_period_end BOOLEAN,p_attempt_id UUID DEFAULT NULL,p_payment_confirmed BOOLEAN DEFAULT FALSE
)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE profile public.profiles%ROWTYPE; current_id TEXT; entitlement TEXT; state TEXT; cancellation_confirmed BOOLEAN;
BEGIN
    IF p_provider NOT IN ('stripe','isracard') OR p_subscription_id IS NULL OR p_plan NOT IN ('free','pro','premium')
       OR p_status NOT IN ('active','trialing','past_due','pending_cancellation','canceled','unpaid','incomplete','incomplete_expired','paused') THEN
        RAISE EXCEPTION 'invalid subscription snapshot';
    END IF;
    SELECT * INTO profile FROM public.profiles WHERE user_id=p_user_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'billing profile missing'; END IF;
    current_id=coalesce(profile.provider_subscription_id,profile.stripe_subscription_id);
    IF current_id IS NOT NULL AND current_id<>p_subscription_id AND profile.subscription_status NOT IN ('canceled','incomplete_expired') THEN
        RETURN jsonb_build_object('applied',false,'reason','different_subscription');
    END IF;
    IF current_id=p_subscription_id AND profile.subscription_status='canceled' AND p_status<>'canceled' THEN
        RETURN jsonb_build_object('applied',false,'reason','terminal_subscription');
    END IF;
    IF current_id=p_subscription_id AND p_status IN ('active','trialing','past_due','pending_cancellation')
       AND p_period_end<coalesce(profile.subscription_expires_at,profile.subscription_end_date) THEN
        RETURN jsonb_build_object('applied',false,'reason','older_period');
    END IF;
    IF profile.subscription_provider IS NOT NULL AND current_id=p_subscription_id AND profile.subscription_provider<>p_provider THEN
        RETURN jsonb_build_object('applied',false,'reason','different_provider');
    END IF;
    -- An unpaid renewal may update provider status, but cannot extend access.
    IF NOT p_payment_confirmed AND (p_period_end IS NULL OR profile.subscription_expires_at IS NULL OR p_period_end>profile.subscription_expires_at) THEN
        p_period_end=profile.subscription_expires_at;
    END IF;
    cancellation_confirmed=p_cancel_at_period_end OR EXISTS (
      SELECT 1 FROM public.subscription_cancellations WHERE user_id=p_user_id AND provider=p_provider
        AND provider_subscription_id=p_subscription_id AND status='confirmed');
    entitlement=CASE WHEN p_status IN ('active','trialing','past_due','pending_cancellation') AND p_period_end>now() THEN p_plan ELSE 'free' END;
    state=CASE WHEN cancellation_confirmed AND entitlement<>'free' THEN 'pending_cancellation' ELSE p_status END;
    UPDATE public.profiles SET plan_type=entitlement,subscription_status=state,
      subscription_provider=p_provider,provider_subscription_id=p_subscription_id,provider_customer_id=p_customer_id,
      stripe_subscription_id=CASE WHEN p_provider='stripe' THEN p_subscription_id ELSE stripe_subscription_id END,
      stripe_customer_id=CASE WHEN p_provider='stripe' THEN p_customer_id ELSE stripe_customer_id END,
      subscription_start_date=CASE WHEN current_id=p_subscription_id THEN coalesce(subscription_start_date,p_period_start) ELSE p_period_start END,
      subscription_end_date=p_period_end,subscription_expires_at=p_period_end,
      auto_renew=NOT cancellation_confirmed AND p_status NOT IN ('canceled','unpaid','incomplete_expired'),updated_at=now()
      WHERE user_id=p_user_id;
    UPDATE public.businesses SET subscription_tier=entitlement,subscription_status=state WHERE owner_id=p_user_id;
    IF p_payment_confirmed AND p_attempt_id IS NOT NULL AND p_status IN ('active','trialing','past_due','pending_cancellation') THEN
        UPDATE public.subscription_checkout_attempts SET status='completed',updated_at=now()
          WHERE id=p_attempt_id AND user_id=p_user_id AND provider=p_provider AND status IN ('creating','open');
    END IF;
    RETURN jsonb_build_object('applied',true,'plan_type',entitlement,'subscription_status',state);
END;
$$;

REVOKE ALL ON FUNCTION public.claim_subscription_checkout(UUID,TEXT,TEXT) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.finish_subscription_checkout(UUID,UUID,TEXT,TEXT,TEXT) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.request_subscription_cancellation(UUID,TEXT,TEXT,TEXT,BOOLEAN) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.confirm_subscription_cancellation(UUID,UUID,TEXT) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.apply_subscription_snapshot(UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,BOOLEAN,UUID,BOOLEAN) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_subscription_checkout(UUID,TEXT,TEXT),public.finish_subscription_checkout(UUID,UUID,TEXT,TEXT,TEXT),
  public.request_subscription_cancellation(UUID,TEXT,TEXT,TEXT,BOOLEAN),public.confirm_subscription_cancellation(UUID,UUID,TEXT),
  public.apply_subscription_snapshot(UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,BOOLEAN,UUID,BOOLEAN) TO service_role;
NOTIFY pgrst,'reload schema';
