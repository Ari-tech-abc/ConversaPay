-- Atomic tenant-scoped deletion and a durable, private email outbox.
-- Older installations may have the keys table without optional display fields.
ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS last_used_at timestamptz;
ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS key_prefix text NOT NULL DEFAULT '';
ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS permissions jsonb NOT NULL DEFAULT '["widget"]'::jsonb;
CREATE OR REPLACE FUNCTION public.delete_products_bulk(
    p_user_id uuid, p_business_id uuid, p_product_ids uuid[],
    p_all_products boolean, p_expected_count integer
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE selected_ids uuid[]; deleted_count integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM businesses WHERE id=p_business_id AND owner_id=p_user_id) THEN
        RAISE EXCEPTION 'Business not found';
    END IF;
    IF p_expected_count <= 0 OR (NOT p_all_products AND
        (cardinality(p_product_ids) <> p_expected_count OR cardinality(p_product_ids)>500)) THEN
        RAISE EXCEPTION 'Invalid selection';
    END IF;
    SELECT array_agg(id) INTO selected_ids FROM (
        SELECT id FROM products WHERE business_id=p_business_id
        AND (p_all_products OR id=ANY(p_product_ids)) FOR UPDATE
    ) locked_products;
    IF coalesce(cardinality(selected_ids),0) <> p_expected_count THEN
        RAISE EXCEPTION 'Selection changed';
    END IF;
    DELETE FROM products WHERE business_id=p_business_id AND id=ANY(selected_ids);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END $$;
REVOKE ALL ON FUNCTION public.delete_products_bulk(uuid,uuid,uuid[],boolean,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.delete_products_bulk(uuid,uuid,uuid[],boolean,integer) TO service_role;

CREATE TABLE IF NOT EXISTS public.notification_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    category text NOT NULL CHECK(category IN ('payment_success','weekly_digest','security_alerts','product_updates')),
    event_key text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}',
    message jsonb,
    first_attempt_at timestamptz,
    status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','sent','skipped','failed')),
    attempts integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    provider_id text,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,
    UNIQUE(user_id,category,event_key)
);
CREATE INDEX IF NOT EXISTS notification_outbox_pending_idx ON public.notification_outbox(available_at) WHERE status IN ('pending','sending');
ALTER TABLE public.notification_outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.notification_outbox FROM anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.notification_outbox TO service_role;

CREATE OR REPLACE FUNCTION public.enqueue_notification(p_user_id uuid,p_category text,p_event_key text,p_payload jsonb)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path=public AS $$
    INSERT INTO notification_outbox(user_id,category,event_key,payload)
    SELECT p_user_id,p_category,p_event_key,p_payload
    FROM profiles p WHERE p.user_id=p_user_id AND p.email_verified IS TRUE
      AND coalesce((p.notification_preferences->>p_category)::boolean,p_category<>'product_updates')
    ON CONFLICT(user_id,category,event_key) DO NOTHING;
$$;
REVOKE ALL ON FUNCTION public.enqueue_notification(uuid,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.enqueue_notification(uuid,text,text,jsonb) TO service_role;

CREATE OR REPLACE FUNCTION public.notify_paid_order() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE owner_uuid uuid;
BEGIN
    IF NEW.status='paid' AND (TG_OP='INSERT' OR OLD.status IS DISTINCT FROM NEW.status) THEN
        SELECT owner_id INTO owner_uuid FROM businesses WHERE id=NEW.business_id;
        PERFORM enqueue_notification(owner_uuid,'payment_success','order:'||NEW.id,
            jsonb_build_object('order_number',NEW.order_number,'total',NEW.total,'currency',NEW.currency));
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS notify_paid_order ON public.orders;
CREATE TRIGGER notify_paid_order AFTER INSERT OR UPDATE OF status ON public.orders FOR EACH ROW EXECUTE FUNCTION public.notify_paid_order();

-- Auth's own password change captures both recovery and authenticated changes.
CREATE OR REPLACE FUNCTION public.notify_password_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
    IF OLD.encrypted_password IS DISTINCT FROM NEW.encrypted_password THEN
        PERFORM enqueue_notification(NEW.id,'security_alerts','password:'||gen_random_uuid(),
            jsonb_build_object('action','password_changed','occurred_at',now()));
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS notify_password_change ON auth.users;
CREATE TRIGGER notify_password_change AFTER UPDATE OF encrypted_password ON auth.users FOR EACH ROW EXECUTE FUNCTION public.notify_password_change();

CREATE OR REPLACE FUNCTION public.notify_api_key_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE owner_uuid uuid; action_name text;
BEGIN
    IF TG_OP='INSERT' THEN action_name='api_key_created';
    ELSIF OLD.is_active IS TRUE AND NEW.is_active IS FALSE THEN action_name='api_key_revoked';
    ELSE RETURN NEW; END IF;
    SELECT owner_id INTO owner_uuid FROM businesses WHERE id=NEW.business_id;
    PERFORM enqueue_notification(owner_uuid,'security_alerts','key:'||NEW.id||':'||action_name,
        jsonb_build_object('action',action_name,'name',NEW.name,'occurred_at',now()));
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS notify_api_key_change ON public.api_keys;
CREATE TRIGGER notify_api_key_change AFTER INSERT OR UPDATE OF is_active ON public.api_keys FOR EACH ROW EXECUTE FUNCTION public.notify_api_key_change();

CREATE TABLE IF NOT EXISTS public.product_announcements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text NOT NULL,
    body text NOT NULL, published_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.product_announcements ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.product_announcements FROM anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.product_announcements TO service_role;
CREATE OR REPLACE FUNCTION public.notify_product_announcement() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
    INSERT INTO notification_outbox(user_id,category,event_key,payload)
    SELECT user_id,'product_updates','release:'||NEW.id,jsonb_build_object('title',NEW.title,'body',NEW.body)
    FROM profiles WHERE email_verified IS TRUE AND notification_preferences->>'product_updates'='true'
    ON CONFLICT(user_id,category,event_key) DO NOTHING;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS notify_product_announcement ON public.product_announcements;
CREATE TRIGGER notify_product_announcement AFTER INSERT ON public.product_announcements FOR EACH ROW EXECUTE FUNCTION public.notify_product_announcement();

-- Count persisted customer messages, rather than an unwritten usage table.
CREATE OR REPLACE FUNCTION public.account_activity(p_user_id uuid,p_start timestamptz,p_end timestamptz)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
    SELECT jsonb_build_object(
      'messages',(SELECT count(*) FROM messages m JOIN conversations c ON c.id=m.conversation_id JOIN businesses b ON b.id=c.business_id
                  WHERE b.owner_id=p_user_id AND m.role='user' AND m.created_at>=p_start AND m.created_at<p_end),
      'conversations',(SELECT count(*) FROM conversations c JOIN businesses b ON b.id=c.business_id
                  WHERE b.owner_id=p_user_id AND c.started_at>=p_start AND c.started_at<p_end),
      'orders',(SELECT count(*) FROM orders o JOIN businesses b ON b.id=o.business_id
                  WHERE b.owner_id=p_user_id AND o.created_at>=p_start AND o.created_at<p_end),
      'paid_orders',(SELECT count(*) FROM orders o JOIN businesses b ON b.id=o.business_id
                  WHERE b.owner_id=p_user_id AND o.status IN ('paid','shipped','delivered') AND EXISTS
                    (SELECT 1 FROM payments pt WHERE pt.order_id=o.id AND pt.status='succeeded' AND pt.paid_at>=p_start AND pt.paid_at<p_end)),
      'revenue_by_currency',(SELECT coalesce(jsonb_object_agg(currency,revenue),'{}'::jsonb) FROM (
                  SELECT o.currency,sum(o.total) revenue FROM orders o JOIN businesses b ON b.id=o.business_id
                  WHERE b.owner_id=p_user_id AND o.status IN ('paid','shipped','delivered') AND EXISTS
                    (SELECT 1 FROM payments pt WHERE pt.order_id=o.id AND pt.status='succeeded' AND pt.paid_at>=p_start AND pt.paid_at<p_end) GROUP BY o.currency) totals)
    );
$$;
REVOKE ALL ON FUNCTION public.account_activity(uuid,timestamptz,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.account_activity(uuid,timestamptz,timestamptz) TO service_role;

CREATE OR REPLACE FUNCTION public.enqueue_weekly_digests() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE period_end timestamptz := date_trunc('week',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
BEGIN
    INSERT INTO notification_outbox(user_id,category,event_key,payload)
    SELECT user_id,'weekly_digest','week:'||period_end,
        account_activity(user_id,period_end-interval '7 days',period_end)||jsonb_build_object('period_start',period_end-interval '7 days','period_end',period_end)
    FROM profiles WHERE email_verified IS TRUE AND created_at<period_end
      AND coalesce((notification_preferences->>'weekly_digest')::boolean,true)
    ON CONFLICT(user_id,category,event_key) DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION public.enqueue_weekly_digests() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.enqueue_weekly_digests() TO service_role;

CREATE OR REPLACE FUNCTION public.claim_notifications(p_limit integer DEFAULT 10)
RETURNS SETOF public.notification_outbox LANGUAGE sql SECURITY DEFINER SET search_path=public AS $$
    UPDATE notification_outbox SET status='sending',attempts=attempts+1,claimed_at=now(),first_attempt_at=coalesce(first_attempt_at,now())
    WHERE id IN (SELECT id FROM notification_outbox
      WHERE (status='pending' AND available_at<=now()) OR (status='sending' AND claimed_at<now()-interval '5 minutes')
      ORDER BY created_at LIMIT least(greatest(p_limit,1),10) FOR UPDATE SKIP LOCKED)
    RETURNING *;
$$;
REVOKE ALL ON FUNCTION public.claim_notifications(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_notifications(integer) TO service_role;
REVOKE ALL ON FUNCTION public.notify_paid_order(), public.notify_password_change(), public.notify_api_key_change(), public.notify_product_announcement() FROM PUBLIC,anon,authenticated;
NOTIFY pgrst, 'reload schema';
