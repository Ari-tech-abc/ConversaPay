-- Dashboard service-role read access
-- The backend uses the Supabase service_role client for authenticated dashboard reads.
-- Keep RLS enabled; these grants only allow the backend role to query the tables.

GRANT SELECT ON TABLE public.orders TO service_role;
GRANT SELECT ON TABLE public.products TO service_role;
GRANT SELECT ON TABLE public.conversations TO service_role;
GRANT SELECT ON TABLE public.businesses TO service_role;
GRANT SELECT ON TABLE public.profiles TO service_role;


GRANT INSERT ON TABLE public.conversations TO service_role;
GRANT UPDATE ON TABLE public.conversations TO service_role;
GRANT SELECT ON TABLE public.messages TO service_role;
GRANT INSERT ON TABLE public.messages TO service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.products TO service_role;
