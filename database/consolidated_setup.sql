-- Idempotent bootstrap for the security-critical tables owned by this repository.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS public.webhook_events (id uuid primary key default uuid_generate_v4(), provider varchar(50) not null, event_id varchar(255) not null, status varchar(50) default 'received', received_at timestamptz default now() not null, processed_at timestamptz, last_error text, unique(provider,event_id));
CREATE INDEX IF NOT EXISTS idx_webhook_events_provider_event ON public.webhook_events(provider,event_id);
ALTER TABLE public.webhook_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.webhook_events FROM anon, authenticated;
GRANT ALL ON public.webhook_events TO service_role;

DO $$ BEGIN
  IF to_regclass('public.businesses') IS NOT NULL THEN
    ALTER TABLE public.businesses ENABLE ROW LEVEL SECURITY;
  END IF;
  IF to_regclass('public.profiles') IS NOT NULL THEN
    ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_expires_at timestamptz;
  END IF;
  IF to_regclass('public.admin_users') IS NOT NULL THEN
    ALTER TABLE public.admin_users ADD COLUMN IF NOT EXISTS username text;
    CREATE UNIQUE INDEX IF NOT EXISTS admin_users_username_lower_key ON public.admin_users (lower(username)) WHERE username IS NOT NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.site_builder_tokens (id uuid primary key default gen_random_uuid(), user_id uuid not null, token_hash text not null unique, expires_at timestamptz not null, used_at timestamptz);
CREATE INDEX IF NOT EXISTS site_builder_tokens_user_idx ON public.site_builder_tokens(user_id, expires_at desc);
ALTER TABLE public.site_builder_tokens ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.site_builder_tokens FROM anon, authenticated;
GRANT ALL ON public.site_builder_tokens TO service_role;

CREATE TABLE IF NOT EXISTS public.site_builder_projects (id uuid primary key default gen_random_uuid(), user_id uuid not null, token_id uuid not null, project_name text not null, html text not null, created_at timestamptz default now(), updated_at timestamptz default now());
CREATE INDEX IF NOT EXISTS site_builder_projects_user_idx ON public.site_builder_projects(user_id, created_at desc);
ALTER TABLE public.site_builder_projects ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.site_builder_projects FROM anon, authenticated;
GRANT ALL ON public.site_builder_projects TO service_role;

CREATE TABLE IF NOT EXISTS public.lead_submissions (id uuid primary key default gen_random_uuid(), business_id uuid not null, name text not null, email text not null, company text, message text not null, source text not null default 'site-builder', page_url text, ip_address inet, user_agent text, status text not null default 'new', created_at timestamptz default now(), updated_at timestamptz default now());
CREATE INDEX IF NOT EXISTS lead_submissions_business_created_idx ON public.lead_submissions(business_id,created_at desc);
ALTER TABLE public.lead_submissions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF to_regclass('public.businesses') IS NOT NULL THEN
    DROP POLICY IF EXISTS lead_submissions_owner_select ON public.lead_submissions;
    CREATE POLICY lead_submissions_owner_select ON public.lead_submissions FOR SELECT TO authenticated USING (public.user_owns_business(business_id));
    DROP POLICY IF EXISTS lead_submissions_owner_update ON public.lead_submissions;
    CREATE POLICY lead_submissions_owner_update ON public.lead_submissions FOR UPDATE TO authenticated USING (public.user_owns_business(business_id)) WITH CHECK (public.user_owns_business(business_id));
  END IF;
END $$;
