-- SaaS profile fields. Apply in Supabase SQL editor before enabling the profile controls.
alter table public.profiles add column if not exists company_name text;
alter table public.profiles add column if not exists timezone text not null default 'UTC';
alter table public.profiles add column if not exists avatar_url text;
alter table public.profiles add column if not exists two_factor_enabled boolean not null default false;
alter table public.profiles add column if not exists notification_preferences jsonb not null default '{"payment_success":true,"weekly_digest":true,"security_alerts":true,"product_updates":false}'::jsonb;
create index if not exists profiles_two_factor_enabled_idx on public.profiles(two_factor_enabled);
