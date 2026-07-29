-- RLS Policy for payments table: read-only access scoped to business owner.
-- Users can only SELECT payments belonging to businesses they own.
-- Write access remains exclusive to service_role (via Stripe webhook processing).

do $$
begin
  if exists (
    select 1 from information_schema.tables
    where table_schema = 'public' and table_name = 'payments'
  ) then
    -- Enable RLS on payments
    execute 'alter table public.payments enable row level security';

    -- Drop existing policies if any (idempotent)
    execute 'drop policy if exists payments_owner_read on public.payments';
    execute 'drop policy if exists payments_service_all on public.payments';

    -- Read-only policy: authenticated users can only SELECT payments for their businesses
    if exists (
      select 1 from information_schema.columns
      where table_schema = 'public' and table_name = 'payments' and column_name = 'business_id'
    ) then
      execute 'create policy payments_owner_read on public.payments for select to authenticated using (public.user_owns_business(business_id))';
    end if;

    -- Revoke all direct access from anonymous role
    execute 'revoke all on public.payments from anon';

    -- Ensure service_role retains full access (webhook writes)
    execute 'grant all on public.payments to service_role';
  end if;
end $$;
