-- Billing foundations for usage metering and dunning.
create table if not exists public.usage_events (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  user_id uuid,
  metric text not null,
  quantity integer not null default 1 check (quantity > 0),
  source text not null,
  idempotency_key text,
  occurred_at timestamptz not null default now(),
  unique(business_id, idempotency_key)
);
create index if not exists usage_events_business_metric_idx
  on public.usage_events(business_id, metric, occurred_at desc);

create table if not exists public.billing_dunning_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  provider text not null,
  provider_event_id text,
  attempt_number integer not null default 1,
  status text not null default 'scheduled',
  next_attempt_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(provider, provider_event_id)
);

alter table public.usage_events enable row level security;
alter table public.billing_dunning_attempts enable row level security;
revoke all on public.usage_events, public.billing_dunning_attempts from anon, authenticated;
grant all on public.usage_events, public.billing_dunning_attempts to service_role;
