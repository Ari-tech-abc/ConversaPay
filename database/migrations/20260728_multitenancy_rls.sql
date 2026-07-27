-- Phase 2 tenant isolation baseline.
-- Service-role backend calls continue to work; browser roles are restricted
-- to rows owned by the authenticated Supabase user.

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.businesses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webhooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS profiles_owner_select ON public.profiles;
CREATE POLICY profiles_owner_select ON public.profiles FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS businesses_owner_all ON public.businesses;
CREATE POLICY businesses_owner_all ON public.businesses FOR ALL USING (owner_id = auth.uid()) WITH CHECK (owner_id = auth.uid());

DROP POLICY IF EXISTS products_business_owner_all ON public.products;
CREATE POLICY products_business_owner_all ON public.products FOR ALL USING (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = products.business_id AND b.owner_id = auth.uid())
) WITH CHECK (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = products.business_id AND b.owner_id = auth.uid())
);

DROP POLICY IF EXISTS orders_business_owner_all ON public.orders;
CREATE POLICY orders_business_owner_all ON public.orders FOR ALL USING (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = orders.business_id AND b.owner_id = auth.uid())
) WITH CHECK (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = orders.business_id AND b.owner_id = auth.uid())
);

DROP POLICY IF EXISTS payments_business_owner_all ON public.payments;
CREATE POLICY payments_business_owner_all ON public.payments FOR ALL USING (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = payments.business_id AND b.owner_id = auth.uid())
) WITH CHECK (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = payments.business_id AND b.owner_id = auth.uid())
);

DROP POLICY IF EXISTS webhooks_business_owner_all ON public.webhooks;
CREATE POLICY webhooks_business_owner_all ON public.webhooks FOR ALL USING (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = webhooks.business_id AND b.owner_id = auth.uid())
) WITH CHECK (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = webhooks.business_id AND b.owner_id = auth.uid())
);

DROP POLICY IF EXISTS api_keys_business_owner_all ON public.api_keys;
CREATE POLICY api_keys_business_owner_all ON public.api_keys FOR ALL USING (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = api_keys.business_id AND b.owner_id = auth.uid())
) WITH CHECK (
  EXISTS (SELECT 1 FROM public.businesses b WHERE b.id = api_keys.business_id AND b.owner_id = auth.uid())
);
