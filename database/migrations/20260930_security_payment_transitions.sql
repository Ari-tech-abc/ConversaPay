-- Replace the legacy overload so PostgREST resolves one unambiguous RPC.
DROP FUNCTION IF EXISTS public.update_order_payment_atomic(UUID, TEXT, TEXT, JSONB, BOOLEAN);
CREATE OR REPLACE FUNCTION public.update_order_payment_atomic(
    p_order_id UUID, p_order_status TEXT, p_payment_status TEXT,
    p_metadata_updates JSONB DEFAULT '{}'::jsonb, p_paid BOOLEAN DEFAULT FALSE,
    p_expected_amount NUMERIC DEFAULT NULL, p_expected_currency TEXT DEFAULT NULL,
    p_provider_session_id TEXT DEFAULT NULL, p_provider TEXT DEFAULT 'stripe'
)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE order_row public.orders%ROWTYPE; payment_row public.payments%ROWTYPE;
BEGIN
    IF p_expected_amount IS NULL OR p_expected_amount <= 0
       OR p_expected_currency IS NULL OR p_provider_session_id IS NULL
       OR p_provider NOT IN ('stripe', 'payme')
       OR p_payment_status NOT IN ('pending', 'processing', 'succeeded', 'failed')
       OR p_order_status NOT IN ('pending', 'processing', 'paid')
       OR (p_paid AND (p_payment_status <> 'succeeded' OR p_order_status <> 'paid'))
       OR (NOT p_paid AND (p_payment_status = 'succeeded' OR p_order_status = 'paid')) THEN
        RETURN FALSE;
    END IF;
    SELECT * INTO order_row FROM public.orders WHERE id = p_order_id FOR UPDATE;
    IF NOT FOUND OR order_row.total <> p_expected_amount
       OR upper(order_row.currency) <> upper(p_expected_currency) THEN RETURN FALSE; END IF;
    SELECT * INTO payment_row FROM public.payments
        WHERE order_id = p_order_id AND business_id = order_row.business_id
          AND metadata->>'provider' = p_provider
          AND coalesce(metadata->>'provider_session_id', metadata->>'session_id') = p_provider_session_id
        ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
    IF NOT FOUND OR payment_row.amount <> p_expected_amount
       OR upper(payment_row.currency) <> upper(p_expected_currency) THEN RETURN FALSE; END IF;
    -- Never revive canceled/refunded orders or regress a successful payment.
    IF order_row.status IN ('canceled', 'refunded') OR payment_row.status IN ('canceled', 'refunded') THEN RETURN TRUE; END IF;
    IF NOT p_paid AND (order_row.status IN ('paid', 'shipped', 'delivered') OR payment_row.status = 'succeeded') THEN RETURN TRUE; END IF;
    UPDATE public.orders SET
        status = CASE WHEN status IN ('shipped', 'delivered') THEN status ELSE p_order_status END,
        payment_status = p_payment_status, updated_at = now()
        WHERE id = p_order_id;
    UPDATE public.payments SET status = p_payment_status,
        metadata = coalesce(metadata, '{}'::jsonb) || coalesce(p_metadata_updates, '{}'::jsonb),
        paid_at = CASE WHEN p_paid THEN coalesce(paid_at, now()) ELSE paid_at END,
        updated_at = now() WHERE id = payment_row.id;
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.update_order_payment_atomic(UUID,TEXT,TEXT,JSONB,BOOLEAN,NUMERIC,TEXT,TEXT,TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.update_order_payment_atomic(UUID,TEXT,TEXT,JSONB,BOOLEAN,NUMERIC,TEXT,TEXT,TEXT) TO service_role;
NOTIFY pgrst, 'reload schema';
