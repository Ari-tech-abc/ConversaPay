-- CI-ONLY. Creates the Supabase-managed objects that
-- database/full_schema_bootstrap.sql depends on but does not create.
-- NEVER apply to a real Supabase project, and never add this path to
-- migration_runner.discover_migrations().
--
-- The bootstrap references three things Supabase provides for free and a
-- vanilla postgres:16 image does not have:
--   1. the anon / authenticated / service_role roles (every GRANT/REVOKE)
--   2. auth.uid()  (user_owns_business + every RLS policy)
--   3. auth.users  (FK from public.site_builder_projects)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
    END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS auth;
GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS auth.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Supabase derives auth.uid() from the request JWT claims. Same GUC here, so
-- tests can impersonate a caller with:
--   select set_config('request.jwt.claim.sub', '<uuid>', true);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS UUID LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;
GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated, service_role;
