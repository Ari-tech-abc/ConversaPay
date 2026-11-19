-- Additive production repairs; do not edit checksummed historical migrations.
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS fulfillment TEXT;
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS stripe_account_id TEXT;
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS shipping NUMERIC(12,2) NOT NULL DEFAULT 0;
ALTER TABLE public.payments ADD COLUMN IF NOT EXISTS refunded_amount NUMERIC(12,2) NOT NULL DEFAULT 0;
ALTER TABLE public.payments ADD COLUMN IF NOT EXISTS reconciliation_checked_at TIMESTAMPTZ;
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS checkout_checked_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS public.inventory_reservations (
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    product_id UUID REFERENCES public.products(id) ON DELETE SET NULL,
    quantity INTEGER NOT NULL CHECK(quantity>0), released BOOLEAN NOT NULL DEFAULT FALSE,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), UNIQUE(order_id,product_id)
);
ALTER TABLE public.inventory_reservations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.inventory_reservations FROM PUBLIC,anon,authenticated;
GRANT ALL ON public.inventory_reservations TO service_role;

CREATE OR REPLACE FUNCTION public.reserve_order_stock() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE entry RECORD; product public.products%ROWTYPE;
BEGIN
    IF jsonb_typeof(NEW.items)<>'array' THEN RAISE EXCEPTION 'invalid order items'; END IF;
    -- Stable key order prevents two baskets from locking products in opposite orders.
    FOR entry IN SELECT item->>'item_key' AS item_key, sum((item->>'quantity')::integer)::integer AS qty
       FROM jsonb_array_elements(NEW.items) item GROUP BY item->>'item_key' ORDER BY item->>'item_key'
    LOOP
        IF entry.qty IS NULL OR entry.qty<1 OR entry.qty>100 THEN RAISE EXCEPTION 'invalid order quantity'; END IF;
        SELECT * INTO product FROM public.products WHERE business_id=NEW.business_id AND item_key=entry.item_key AND is_active FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'product unavailable'; END IF;
        IF product.inventory_count>=0 THEN
            IF product.inventory_count<entry.qty THEN RAISE EXCEPTION 'insufficient stock'; END IF;
            UPDATE public.products SET inventory_count=inventory_count-entry.qty WHERE id=product.id;
            INSERT INTO public.inventory_reservations(order_id,product_id,quantity) VALUES(NEW.id,product.id,entry.qty);
        END IF;
    END LOOP;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS reserve_order_stock ON public.orders;
CREATE TRIGGER reserve_order_stock AFTER INSERT ON public.orders FOR EACH ROW EXECUTE FUNCTION public.reserve_order_stock();

CREATE OR REPLACE FUNCTION public.release_order_stock() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE reservation RECORD;
BEGIN
    IF NEW.status IN ('canceled','refunded') AND OLD.status IS DISTINCT FROM NEW.status THEN
        FOR reservation IN UPDATE public.inventory_reservations SET released=TRUE WHERE order_id=NEW.id AND NOT released RETURNING * LOOP
            UPDATE public.products SET inventory_count=inventory_count+reservation.quantity
              WHERE id=reservation.product_id AND inventory_count>=0;
        END LOOP;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS release_order_stock ON public.orders;
CREATE TRIGGER release_order_stock AFTER UPDATE OF status ON public.orders FOR EACH ROW EXECUTE FUNCTION public.release_order_stock();
REVOKE ALL ON FUNCTION public.reserve_order_stock(),public.release_order_stock() FROM PUBLIC,anon,authenticated;

CREATE OR REPLACE FUNCTION public.claim_webhook_event(p_provider TEXT,p_event_id TEXT,p_event_type TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE entry public.payment_webhook_events%ROWTYPE;
BEGIN
    INSERT INTO public.payment_webhook_events(provider,provider_event_id,event_type,processing_status)
      VALUES(p_provider,p_event_id,p_event_type,'processing') ON CONFLICT(provider,provider_event_id) DO NOTHING;
    IF FOUND THEN RETURN TRUE; END IF;
    SELECT * INTO entry FROM public.payment_webhook_events WHERE provider=p_provider AND provider_event_id=p_event_id FOR UPDATE;
    IF entry.processing_status='processed' THEN RETURN FALSE; END IF;
    IF entry.processing_status='processing' AND entry.updated_at>now()-interval '5 minutes' THEN
        RAISE EXCEPTION 'webhook processing in progress'; -- retry, never acknowledge unfinished work
    END IF;
    UPDATE public.payment_webhook_events SET processing_status='processing',error_message=NULL,processed_at=NULL
      WHERE id=entry.id;
    RETURN TRUE;
END $$;

CREATE OR REPLACE FUNCTION public.expire_order_checkout(p_order_id UUID,p_session_id TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE target public.orders%ROWTYPE;
BEGIN
    SELECT * INTO target FROM public.orders WHERE id=p_order_id FOR UPDATE;
    IF NOT FOUND OR target.payment_status IN ('succeeded','paid') THEN RETURN FALSE; END IF;
    IF NOT EXISTS(SELECT 1 FROM public.payments WHERE order_id=p_order_id AND metadata->>'provider_session_id'=p_session_id) THEN RETURN FALSE; END IF;
    UPDATE public.payments SET status='canceled',updated_at=now() WHERE order_id=p_order_id AND status IN ('pending','processing');
    UPDATE public.orders SET status='canceled',payment_status='canceled',updated_at=now() WHERE id=p_order_id;
    RETURN TRUE;
END $$;

CREATE OR REPLACE FUNCTION public.apply_order_refund(p_payment_intent TEXT,p_account TEXT,p_amount NUMERIC)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE payment public.payments%ROWTYPE;
BEGIN
    SELECT * INTO payment FROM public.payments WHERE metadata->>'payment_intent'=p_payment_intent
      AND coalesce(metadata->>'stripe_account_id','')=coalesce(p_account,'') FOR UPDATE;
    IF NOT FOUND THEN RETURN FALSE; END IF;
    IF p_amount<0 OR p_amount>payment.amount THEN RAISE EXCEPTION 'invalid refund amount'; END IF;
    -- Charge.amount_refunded is cumulative: duplicates and out-of-order events cannot regress it.
    UPDATE public.payments SET refunded_amount=greatest(refunded_amount,p_amount),
       status=CASE WHEN p_amount=amount THEN 'refunded' ELSE status END,updated_at=now() WHERE id=payment.id;
    IF p_amount=payment.amount THEN
        UPDATE public.orders SET status='refunded',payment_status='refunded',updated_at=now() WHERE id=payment.order_id;
    END IF;
    RETURN TRUE;
END $$;

CREATE TABLE IF NOT EXISTS public.merchant_connect_states (
    token_hash TEXT PRIMARY KEY,user_id UUID NOT NULL,business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE public.merchant_connect_states ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.merchant_connect_states FROM PUBLIC,anon,authenticated;
GRANT ALL ON public.merchant_connect_states TO service_role;
CREATE OR REPLACE FUNCTION public.consume_merchant_connect_state(p_hash TEXT)
RETURNS SETOF public.merchant_connect_states LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
    DELETE FROM public.merchant_connect_states WHERE token_hash=p_hash AND expires_at>now() RETURNING *;
$$;

CREATE TABLE IF NOT EXISTS public.account_deletions (
    user_id UUID PRIMARY KEY,status TEXT NOT NULL DEFAULT 'requested',requested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.account_deletions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.account_deletions FROM PUBLIC,anon,authenticated;
GRANT ALL ON public.account_deletions TO service_role;
CREATE OR REPLACE FUNCTION public.begin_account_deletion(p_user_id UUID)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
    PERFORM 1 FROM public.profiles WHERE user_id=p_user_id FOR UPDATE;
    INSERT INTO public.account_deletions(user_id) VALUES(p_user_id) ON CONFLICT DO NOTHING;
    UPDATE public.businesses SET is_active=FALSE WHERE owner_id=p_user_id;
    UPDATE public.api_keys SET is_active=FALSE WHERE business_id IN (SELECT id FROM public.businesses WHERE owner_id=p_user_id);
END $$;
CREATE OR REPLACE FUNCTION public.purge_account_data(p_user_id UUID)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public.account_deletions WHERE user_id=p_user_id) THEN RAISE EXCEPTION 'deletion not requested'; END IF;
    DELETE FROM public.logs WHERE business_id IN (SELECT id FROM public.businesses WHERE owner_id=p_user_id);
    DELETE FROM public.usage_logs WHERE business_id IN (SELECT id FROM public.businesses WHERE owner_id=p_user_id);
    DELETE FROM public.usage_events WHERE business_id IN (SELECT id FROM public.businesses WHERE owner_id=p_user_id);
    DELETE FROM public.admin_audit_logs WHERE business_id IN (SELECT id FROM public.businesses WHERE owner_id=p_user_id);
    DELETE FROM public.businesses WHERE owner_id=p_user_id;
    DELETE FROM public.notification_outbox WHERE user_id=p_user_id;
    DELETE FROM public.subscription_cancellations WHERE user_id=p_user_id;
    DELETE FROM public.subscription_checkout_attempts WHERE user_id=p_user_id;
    DELETE FROM public.refund_requests WHERE user_id=p_user_id;
    DELETE FROM public.billing_dunning_attempts WHERE user_id=p_user_id;
    DELETE FROM public.site_builder_tokens WHERE user_id=p_user_id;
    DELETE FROM public.usage_logs WHERE user_id=p_user_id;
    DELETE FROM public.usage_events WHERE user_id=p_user_id;
    DELETE FROM public.profiles WHERE user_id=p_user_id;
    UPDATE public.account_deletions SET status='completed' WHERE user_id=p_user_id;
END $$;
REVOKE ALL ON FUNCTION public.expire_order_checkout(UUID,TEXT),public.apply_order_refund(TEXT,TEXT,NUMERIC),
  public.consume_merchant_connect_state(TEXT),public.begin_account_deletion(UUID),public.purge_account_data(UUID) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.expire_order_checkout(UUID,TEXT),public.apply_order_refund(TEXT,TEXT,NUMERIC),
  public.consume_merchant_connect_state(TEXT),public.begin_account_deletion(UUID),public.purge_account_data(UUID) TO service_role;
NOTIFY pgrst,'reload schema';

CREATE OR REPLACE FUNCTION public.bind_merchant_account(p_business_id UUID,p_user_id UUID,p_account TEXT,p_ready BOOLEAN)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
    PERFORM 1 FROM public.businesses WHERE id=p_business_id AND owner_id=p_user_id AND is_active FOR UPDATE;
    IF NOT FOUND OR p_account NOT LIKE 'acct_%' THEN RAISE EXCEPTION 'invalid merchant binding'; END IF;
    IF EXISTS(SELECT 1 FROM public.orders WHERE business_id=p_business_id AND status IN ('pending','processing')) THEN
       RAISE EXCEPTION 'pending checkout must finish before changing merchant account';
    END IF;
    UPDATE public.payment_accounts SET stripe_account_id=p_account,status=CASE WHEN p_ready THEN 'active' ELSE 'pending' END
       WHERE business_id=p_business_id AND provider='stripe' AND status<>'revoked';
    IF NOT FOUND THEN
       INSERT INTO public.payment_accounts(business_id,provider,stripe_account_id,status)
          VALUES(p_business_id,'stripe',p_account,CASE WHEN p_ready THEN 'active' ELSE 'pending' END);
    END IF;
END $$;
REVOKE ALL ON FUNCTION public.bind_merchant_account(UUID,UUID,TEXT,BOOLEAN) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.bind_merchant_account(UUID,UUID,TEXT,BOOLEAN) TO service_role;

CREATE OR REPLACE FUNCTION public.business_sales_metrics(p_business_id UUID,p_days INTEGER DEFAULT 30)
RETURNS JSONB LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
WITH scoped AS (
 SELECT o.*,coalesce((SELECT sum(p.refunded_amount) FROM public.payments p WHERE p.order_id=o.id),0) AS refunded
 FROM public.orders o WHERE business_id=p_business_id AND (p_days IS NULL OR created_at>=now()-make_interval(days=>least(greatest(p_days,1),3650)))
), paid AS (
 SELECT *,greatest(total-refunded,0) AS net FROM scoped WHERE currency='ILS' AND payment_status IN ('paid','succeeded') AND status IN ('paid','shipped','delivered')
), conv AS (
 SELECT count(DISTINCT session_id) AS n FROM public.conversations WHERE business_id=p_business_id AND (p_days IS NULL OR started_at>=now()-make_interval(days=>least(greatest(p_days,1),3650)))
), top_products AS (
 SELECT item->>'item_key' AS item_key,max(item->>'name') AS name,sum((item->>'quantity')::integer) AS total_quantity,count(*) AS order_count
 FROM paid CROSS JOIN LATERAL jsonb_array_elements(items) item GROUP BY item->>'item_key'
)
SELECT jsonb_build_object(
 'business_id',p_business_id,'currency','ILS','period_days',p_days,
 'total_revenue',coalesce((SELECT sum(net) FROM paid),0),'closed_deals',(SELECT count(*) FROM paid),
 'paid_orders_count',(SELECT count(*) FROM paid),'total_orders',(SELECT count(*) FROM scoped),
 'total_conversations',(SELECT n FROM conv),'unique_chat_sessions',(SELECT n FROM conv),
 'total_customers',(SELECT count(*) FROM public.customers WHERE business_id=p_business_id),
 'average_order_value',coalesce((SELECT round(avg(net),2) FROM paid),0),
 'conversion_rate',CASE WHEN (SELECT n FROM conv)>0 THEN round(100.0*(SELECT count(*) FROM paid)/(SELECT n FROM conv),2) ELSE 0 END,
 'orders_by_status',coalesce((SELECT jsonb_object_agg(status,n) FROM (SELECT status,count(*) n FROM scoped GROUP BY status) states),'{}'::jsonb),
 'top_selling_products',coalesce((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM top_products ORDER BY total_quantity DESC LIMIT 10) t),'[]'::jsonb),
 'revenue_by_day',coalesce((SELECT jsonb_agg(to_jsonb(d)) FROM (SELECT created_at::date AS date,sum(net) AS revenue FROM paid GROUP BY created_at::date ORDER BY created_at::date) d),'[]'::jsonb),
 'charts_data','[]'::jsonb
);
$$;
REVOKE ALL ON FUNCTION public.business_sales_metrics(UUID,INTEGER) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.business_sales_metrics(UUID,INTEGER) TO service_role;

CREATE OR REPLACE FUNCTION public.save_commerce_settings(p_business_id UUID,p_user_id UUID,p_settings JSONB)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 UPDATE public.businesses SET settings=coalesce(settings,'{}'::jsonb)||p_settings WHERE id=p_business_id AND owner_id=p_user_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'business not found'; END IF;
END $$;
REVOKE ALL ON FUNCTION public.save_commerce_settings(UUID,UUID,JSONB) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.save_commerce_settings(UUID,UUID,JSONB) TO service_role;
