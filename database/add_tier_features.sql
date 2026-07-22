-- Tier feature storage for widget keys and Premium builder sessions.
create table if not exists public.api_keys (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  name text not null,
  key_prefix text not null,
  key_hash text not null unique,
  permissions jsonb not null default '["widget"]'::jsonb,
  is_active boolean not null default true,
  last_used_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists api_keys_business_active_idx on public.api_keys(business_id, is_active);
create table if not exists public.site_builder_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  token_hash text not null unique,
  expires_at timestamptz not null,
  used_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists site_builder_tokens_hash_idx on public.site_builder_tokens(token_hash);
alter table public.api_keys enable row level security;
alter table public.site_builder_tokens enable row level security;
