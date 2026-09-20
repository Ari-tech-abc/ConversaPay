-- Prevent duplicate processing of provider webhook events.
-- Apply after 20260920_payment_hardening.sql.

create table if not exists public.payment_webhook_events (
    id uuid primary key default gen_random_uuid(),
    provider text not null check (provider in ('stripe', 'payme')),
    provider_event_id text not null,
    event_type text,
    payload jsonb not null default '{}'::jsonb,
    processing_status text not null default 'received'
        check (processing_status in ('received', 'processing', 'processed', 'failed')),
    error_message text,
    received_at timestamptz not null default now(),
    processed_at timestamptz,
    updated_at timestamptz not null default now(),
    unique (provider, provider_event_id)
);

create index if not exists idx_payment_webhook_events_status
    on public.payment_webhook_events (processing_status, received_at);

alter table public.payment_webhook_events enable row level security;

revoke all on table public.payment_webhook_events from anon, authenticated;
grant select, insert, update on table public.payment_webhook_events to service_role;

-- Keep updated_at current when an event is retried or completed.
create or replace function public.set_payment_webhook_event_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_payment_webhook_events_updated_at
    on public.payment_webhook_events;

create trigger trg_payment_webhook_events_updated_at
before update on public.payment_webhook_events
for each row execute function public.set_payment_webhook_event_updated_at();
