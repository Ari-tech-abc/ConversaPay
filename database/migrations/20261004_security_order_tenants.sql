-- RLS is bypassed by the backend's service role. Foreign keys alone do not
-- prevent an order in one business from referring to another tenant's data.
CREATE OR REPLACE FUNCTION public.enforce_order_tenant_references()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    IF NEW.customer_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.customers c
        WHERE c.id = NEW.customer_id AND c.business_id = NEW.business_id
    ) THEN
        RAISE EXCEPTION 'Order customer must belong to the same business' USING ERRCODE = '23514';
    END IF;
    IF NEW.conversation_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.conversations c
        WHERE c.id = NEW.conversation_id AND c.business_id = NEW.business_id
    ) THEN
        RAISE EXCEPTION 'Order conversation must belong to the same business' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.enforce_order_tenant_references() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.enforce_order_tenant_references() TO service_role;
DROP TRIGGER IF EXISTS enforce_order_tenant_references ON public.orders;
CREATE TRIGGER enforce_order_tenant_references
BEFORE INSERT OR UPDATE OF business_id, customer_id, conversation_id ON public.orders
FOR EACH ROW EXECUTE FUNCTION public.enforce_order_tenant_references();
