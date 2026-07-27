-- Multi-tenancy hardening. Additive and fail-closed for tenant-owned tables.
-- Service-role backend operations continue to work; browser roles are restricted.

create or replace function public.user_owns_business(target_business_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.businesses b
    where b.id = target_business_id
      and b.owner_id = auth.uid()
  );
$$;

revoke all on function public.user_owns_business(uuid) from public;
grant execute on function public.user_owns_business(uuid) to authenticated;

do $$
declare
  target_table text;
begin
  foreach target_table in array array['businesses','products','orders','payments','api_keys','webhooks'] loop
    if exists (
      select 1 from information_schema.tables t
      where t.table_schema='public' and t.table_name=target_table
    ) then
      execute format('alter table public.%I enable row level security', target_table);
    end if;
  end loop;
end $$;

do $$
begin
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='businesses' and column_name='owner_id') then
    execute 'drop policy if exists businesses_owner_isolation on public.businesses';
    execute 'create policy businesses_owner_isolation on public.businesses for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid())';
  end if;
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='products' and column_name='business_id') then
    execute 'drop policy if exists products_business_isolation on public.products';
    execute 'create policy products_business_isolation on public.products for all to authenticated using (public.user_owns_business(business_id)) with check (public.user_owns_business(business_id))';
  end if;
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='orders' and column_name='business_id') then
    execute 'drop policy if exists orders_business_isolation on public.orders';
    execute 'create policy orders_business_isolation on public.orders for all to authenticated using (public.user_owns_business(business_id)) with check (public.user_owns_business(business_id))';
  end if;
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='api_keys' and column_name='business_id') then
    execute 'drop policy if exists api_keys_business_isolation on public.api_keys';
    execute 'create policy api_keys_business_isolation on public.api_keys for all to authenticated using (public.user_owns_business(business_id)) with check (public.user_owns_business(business_id))';
  end if;
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='webhooks' and column_name='business_id') then
    execute 'drop policy if exists webhooks_business_isolation on public.webhooks';
    execute 'create policy webhooks_business_isolation on public.webhooks for all to authenticated using (public.user_owns_business(business_id)) with check (public.user_owns_business(business_id))';
  end if;
end $$;

do $$
declare
  target_table text;
begin
  foreach target_table in array array['businesses','products','orders','payments','api_keys','webhooks'] loop
    if exists (select 1 from information_schema.tables t where t.table_schema='public' and t.table_name=target_table) then
      execute format('revoke all on public.%I from anon', target_table);
    end if;
  end loop;
end $$;
