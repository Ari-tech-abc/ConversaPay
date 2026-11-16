-- Private billing ledger and requests. No card data or provider response bodies.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS provider_subscription_id TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_sync_checked_at timestamptz;
-- Include existing legacy contracts in recovery without creating new contracts.
UPDATE public.profiles SET provider_subscription_id=stripe_subscription_id,subscription_provider='stripe'
 WHERE provider_subscription_id IS NULL AND stripe_subscription_id IS NOT NULL AND coalesce(subscription_provider,'stripe')='stripe';
CREATE INDEX IF NOT EXISTS profiles_subscription_sync_idx ON public.profiles(subscription_sync_checked_at NULLS FIRST) WHERE provider_subscription_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS public.subscription_invoices (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES public.profiles(user_id) ON DELETE CASCADE,
 provider text NOT NULL CHECK(provider IN ('stripe','isracard')), provider_invoice_id text NOT NULL,
 provider_subscription_id text NOT NULL, status text NOT NULL CHECK(status IN ('paid','failed')),
 amount_minor bigint NOT NULL CHECK(amount_minor>=0), currency text NOT NULL CHECK(currency='ILS'),
 period_start timestamptz, period_end timestamptz, occurred_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(provider,provider_invoice_id)
);
CREATE INDEX IF NOT EXISTS subscription_invoices_user_idx ON public.subscription_invoices(user_id,occurred_at DESC,id);
CREATE TABLE IF NOT EXISTS public.subscription_plan_requests (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES public.profiles(user_id) ON DELETE CASCADE,
 provider_subscription_id text NOT NULL, current_plan text NOT NULL, requested_plan text NOT NULL CHECK(requested_plan IN ('pro','premium')),
 status text NOT NULL DEFAULT 'requested' CHECK(status IN ('requested','withdrawn')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS subscription_plan_request_pending ON public.subscription_plan_requests(user_id) WHERE status='requested';
CREATE TABLE IF NOT EXISTS public.subscription_operational_alerts (
 alert_key text PRIMARY KEY, kind text NOT NULL, operation_id text NOT NULL,
 first_seen_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz
);
ALTER TABLE public.subscription_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscription_plan_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscription_operational_alerts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.subscription_invoices,public.subscription_plan_requests,public.subscription_operational_alerts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.subscription_invoices,public.subscription_plan_requests,public.subscription_operational_alerts TO service_role;

ALTER TABLE public.notification_outbox DROP CONSTRAINT IF EXISTS notification_outbox_category_check;
ALTER TABLE public.notification_outbox ADD CONSTRAINT notification_outbox_category_check
 CHECK(category IN ('payment_success','weekly_digest','security_alerts','product_updates','subscription_billing'));

CREATE OR REPLACE FUNCTION public.record_subscription_invoice(p_user_id uuid,p_provider text,p_subscription_id text,p_invoice_id text,
 p_status text,p_amount bigint,p_currency text,p_start timestamptz,p_end timestamptz,p_occurred timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE profile public.profiles%ROWTYPE; existing public.subscription_invoices%ROWTYPE;
BEGIN
 SELECT * INTO profile FROM public.profiles WHERE user_id=p_user_id FOR UPDATE;
 IF NOT FOUND OR coalesce(profile.provider_subscription_id,profile.stripe_subscription_id) IS DISTINCT FROM p_subscription_id
 OR coalesce(profile.subscription_provider,'stripe') IS DISTINCT FROM p_provider THEN
   RAISE EXCEPTION 'billing_subscription_mismatch';
 END IF;
 IF p_invoice_id IS NULL OR length(p_invoice_id)=0 OR p_status NOT IN ('paid','failed') OR p_occurred IS NULL THEN RAISE EXCEPTION 'invalid invoice'; END IF;
 SELECT * INTO existing FROM public.subscription_invoices WHERE provider=p_provider AND provider_invoice_id=p_invoice_id FOR UPDATE;
 IF FOUND AND (existing.user_id<>p_user_id OR existing.provider_subscription_id<>p_subscription_id) THEN RAISE EXCEPTION 'billing_invoice_mismatch'; END IF;
 IF existing.status='paid' THEN RETURN jsonb_build_object('recorded',true); END IF;
 INSERT INTO public.subscription_invoices(user_id,provider,provider_invoice_id,provider_subscription_id,status,amount_minor,currency,period_start,period_end,occurred_at)
 VALUES(p_user_id,p_provider,p_invoice_id,p_subscription_id,p_status,p_amount,p_currency,p_start,p_end,p_occurred)
 ON CONFLICT(provider,provider_invoice_id) DO UPDATE SET status=EXCLUDED.status,amount_minor=EXCLUDED.amount_minor,
 currency=EXCLUDED.currency,period_start=EXCLUDED.period_start,period_end=EXCLUDED.period_end,updated_at=now();
 PERFORM public.enqueue_notification(p_user_id,'subscription_billing','invoice:'||p_provider||':'||p_invoice_id||':'||p_status,
 jsonb_build_object('action',p_status,'amount_minor',p_amount,'currency',p_currency,'access_until',profile.subscription_expires_at));
 RETURN jsonb_build_object('recorded',true);
END $$;

CREATE OR REPLACE FUNCTION public.request_subscription_plan_change(p_user_id uuid,p_plan text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE profile public.profiles%ROWTYPE; request public.subscription_plan_requests%ROWTYPE;
BEGIN
 SELECT * INTO profile FROM public.profiles WHERE user_id=p_user_id FOR UPDATE;
 IF p_plan NOT IN ('pro','premium') THEN RAISE EXCEPTION 'invalid plan'; END IF;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','billing_plan_change_unavailable'); END IF;
 IF profile.plan_type NOT IN ('pro','premium') OR profile.subscription_expires_at<=now() OR profile.subscription_expires_at IS NULL
 OR profile.subscription_status NOT IN ('active','trialing') OR profile.auto_renew IS NOT TRUE
 OR coalesce(profile.provider_subscription_id,profile.stripe_subscription_id) IS NULL THEN RETURN jsonb_build_object('error','billing_plan_change_unavailable'); END IF;
 IF profile.plan_type=p_plan THEN RETURN jsonb_build_object('error','billing_plan_unchanged'); END IF;
 UPDATE public.subscription_plan_requests SET status='withdrawn',updated_at=now()
 WHERE user_id=p_user_id AND status='requested' AND provider_subscription_id<>coalesce(profile.provider_subscription_id,profile.stripe_subscription_id);
 SELECT * INTO request FROM public.subscription_plan_requests WHERE user_id=p_user_id AND status='requested' FOR UPDATE;
 IF FOUND THEN
   IF request.requested_plan<>p_plan THEN RETURN jsonb_build_object('error','billing_plan_change_pending'); END IF;
   RETURN to_jsonb(request);
 END IF;
 INSERT INTO public.subscription_plan_requests(user_id,provider_subscription_id,current_plan,requested_plan)
 VALUES(p_user_id,coalesce(profile.provider_subscription_id,profile.stripe_subscription_id),profile.plan_type,p_plan) RETURNING * INTO request;
 RETURN to_jsonb(request);
END $$;

CREATE OR REPLACE FUNCTION public.scan_subscription_operations() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE alert_count integer;
BEGIN
 -- Serialize scans, including when two web instances start at the same time.
 PERFORM pg_advisory_xact_lock(731612004);
 UPDATE public.subscription_operational_alerts SET resolved_at=now() WHERE resolved_at IS NULL AND kind<>'sync_failure';
 INSERT INTO public.subscription_operational_alerts(alert_key,kind,operation_id)
 SELECT kind||':'||id,kind,id FROM (
 SELECT 'checkout_unknown' kind,id::text FROM public.subscription_checkout_attempts WHERE status='creating' AND provider_session_id IS NULL AND created_at<now()-interval '15 minutes'
 UNION ALL SELECT 'checkout_unresolved',id::text FROM public.subscription_checkout_attempts WHERE status IN ('creating','open') AND created_at<now()-interval '24 hours'
 UNION ALL SELECT 'cancellation_unconfirmed',id::text FROM public.subscription_cancellations WHERE status='requested' AND created_at<now()-interval '15 minutes'
 UNION ALL SELECT 'plan_change_pending',id::text FROM public.subscription_plan_requests WHERE status='requested' AND created_at<now()-interval '24 hours'
 ) pending ON CONFLICT(alert_key) DO UPDATE SET last_seen_at=now(),resolved_at=NULL;
 SELECT count(*) INTO alert_count FROM public.subscription_operational_alerts WHERE resolved_at IS NULL;
 -- Access checks already enforce the paid-through date. Notify without issuing charges.
 PERFORM public.enqueue_notification(user_id,'subscription_billing','expired:'||subscription_expires_at::text,
 jsonb_build_object('action','expired','access_until',subscription_expires_at))
 FROM public.profiles WHERE subscription_expires_at<=now() AND subscription_expires_at>now()-interval '7 days'
 AND coalesce(provider_subscription_id,stripe_subscription_id) IS NOT NULL;
 RETURN jsonb_build_object('open_alerts',alert_count);
END $$;
CREATE OR REPLACE FUNCTION public.close_obsolete_plan_requests() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 UPDATE public.subscription_plan_requests SET status='withdrawn',updated_at=now()
 WHERE user_id=NEW.user_id AND status='requested' AND (
   provider_subscription_id IS DISTINCT FROM coalesce(NEW.provider_subscription_id,NEW.stripe_subscription_id)
   OR NEW.auto_renew IS FALSE OR NEW.subscription_status IN ('canceled','incomplete_expired')
   OR requested_plan=NEW.plan_type);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.close_obsolete_plan_requests() FROM PUBLIC,anon,authenticated;
DROP TRIGGER IF EXISTS close_obsolete_plan_requests ON public.profiles;
CREATE TRIGGER close_obsolete_plan_requests AFTER UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.close_obsolete_plan_requests();
REVOKE ALL ON FUNCTION public.record_subscription_invoice(uuid,text,text,text,text,bigint,text,timestamptz,timestamptz,timestamptz),
 public.request_subscription_plan_change(uuid,text),public.scan_subscription_operations() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_subscription_invoice(uuid,text,text,text,text,bigint,text,timestamptz,timestamptz,timestamptz),
 public.request_subscription_plan_change(uuid,text),public.scan_subscription_operations() TO service_role;
CREATE OR REPLACE FUNCTION public.subscription_storage_ready() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT jsonb_build_object('ready',
   to_regprocedure('public.claim_subscription_checkout(uuid,text,text)') IS NOT NULL
   AND to_regprocedure('public.confirm_subscription_cancellation(uuid,uuid,text)') IS NOT NULL
   AND to_regprocedure('public.apply_subscription_snapshot(uuid,text,text,text,text,text,timestamptz,timestamptz,boolean,uuid,boolean)') IS NOT NULL
   AND to_regprocedure('public.record_subscription_invoice(uuid,text,text,text,text,bigint,text,timestamptz,timestamptz,timestamptz)') IS NOT NULL
   AND to_regprocedure('public.request_subscription_plan_change(uuid,text)') IS NOT NULL
   AND to_regprocedure('public.scan_subscription_operations()') IS NOT NULL);
$$;
REVOKE ALL ON FUNCTION public.subscription_storage_ready() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.subscription_storage_ready() TO service_role;
NOTIFY pgrst,'reload schema';
