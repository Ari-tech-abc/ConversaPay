-- Atomically update the order and its latest payment for a provider event.
CREATE OR REPLACE FUNCTION public.update_order_payment_atomic(
    p_order_id UUID,
    p_order_status TEXT,
    p_payment_status TEXT,
    p_metadata_updates JSONB DEFAULT '{}'::jsonb,
    p_paid BOOLEAN DEFAULT FALSE
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_payment_id UUID;
    v_now TIMESTAMPTZ := NOW();
BEGIN
    IF p_order_id IS NULL THEN
        RAISE EXCEPTION 'order_id is required';
    END IF;

    UPDATE public.orders
       SET status = p_order_status,
           payment_status = p_payment_status,
           updated_at = v_now
     WHERE id = p_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'order not found: %', p_order_id;
    END IF;

    SELECT id INTO v_payment_id
      FROM public.payments
     WHERE order_id = p_order_id
     ORDER BY created_at DESC
     LIMIT 1
     FOR UPDATE;

    IF v_payment_id IS NULL THEN
        RAISE EXCEPTION 'payment not found for order: %', p_order_id;
    END IF;

    UPDATE public.payments
       SET status = p_payment_status,
           metadata = COALESCE(metadata, '{}'::jsonb) || COALESCE(p_metadata_updates, '{}'::jsonb),
           paid_at = CASE WHEN p_paid THEN v_now ELSE paid_at END,
           updated_at = v_now
     WHERE id = v_payment_id;

    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.update_order_payment_atomic(UUID, TEXT, TEXT, JSONB, BOOLEAN) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.update_order_payment_atomic(UUID, TEXT, TEXT, JSONB, BOOLEAN) TO service_role;
