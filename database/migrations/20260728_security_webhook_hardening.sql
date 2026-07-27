-- Security hardening: make replay protection explicit for external events.
-- Safe additive migration. Run after the base schema.

create table if not exists public.webhook_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  event_id text not null,
  status text not null default 'received',
  received_at timestamptz not null default now(),
  processed_at timestamptz,
  unique(provider, event_id)
);

create index if not exists webhook_events_received_at_idx
  on public.webhook_events(received_at desc);

alter table public.webhook_events enable row level security;
revoke all on public.webhook_events from anon, authenticated;
grant all on public.webhook_events to service_role;
