-- ConversaPay payment hardening migration
-- Apply only after reviewing provider-specific credential storage and RLS policies.

create table if not exists public.payment_accounts (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    provider text not null check (provider in ('stripe', 'payme')),
    status text not null default 'pending' check (status in ('pending', 'active', 'revoked', 'error')),
    stripe_account_id text,
    payme_seller_id text,
    credentials_secret_ref text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint payment_accounts_provider_identity_check check (
        (provider = 'stripe' and stripe_account_id is not null)
        or (provider = 'payme' and payme_seller_id is not null)
        or status = 'pending'
    )
);

create unique index if not exists uq_payment_accounts_business_provider
    on public.payment_accounts (business_id, provider)
    where status <> 'revoked';

create index if not exists idx_payment_accounts_business_id
    on public.payment_accounts (business_id);

alter table public.payment_accounts enable row level security;

 drop policy if exists payment_accounts_owner_select on public.payment_accounts;
create policy payment_accounts_owner_select
    on public.payment_accounts for select
    using (
        exists (
            select 1
            from public.businesses b
            where b.id = payment_accounts.business_id
              and b.owner_id = auth.uid()
        )
    );

 drop policy if exists payment_accounts_owner_insert on public.payment_accounts;
create policy payment_accounts_owner_insert
    on public.payment_accounts for insert
    with check (
        exists (
            select 1
            from public.businesses b
            where b.id = payment_accounts.business_id
              and b.owner_id = auth.uid()
        )
    );

 drop policy if exists payment_accounts_owner_update on public.payment_accounts;
create policy payment_accounts_owner_update
    on public.payment_accounts for update
    using (
        exists (
            select 1
            from public.businesses b
            where b.id = payment_accounts.business_id
              and b.owner_id = auth.uid()
        )
    )
    with check (
        exists (
            select 1
            from public.businesses b
            where b.id = payment_accounts.business_id
              and b.owner_id = auth.uid()
        )
    );

-- Prevent multiple active/pending payment rows for the same order/provider session.
create unique index if not exists uq_payments_order_provider_session
    on public.payments (
        order_id,
        ((metadata ->> 'provider')),
        ((metadata ->> 'provider_session_id'))
    )
    where ((metadata ->> 'provider_session_id') is not null);

-- Used by reconciliation workers.
create index if not exists idx_payments_pending_created_at
    on public.payments (created_at)
    where status = 'pending';
