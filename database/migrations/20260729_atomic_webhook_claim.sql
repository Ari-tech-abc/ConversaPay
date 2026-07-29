-- Atomic Stripe webhook claim with retry-safe failed state.
create or replace function public.claim_webhook_event(p_provider text, p_event_id text, p_event_type text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare claimed boolean := false;
begin
  insert into public.webhook_events(provider, event_id, status, received_at)
  values (p_provider, p_event_id, 'processing', now())
  on conflict (provider, event_id) do nothing;
  if found then return true; end if;
  update public.webhook_events
     set status = 'processing', received_at = now(), status = 'processing'
   where provider = p_provider and event_id = p_event_id and status in ('failed', 'received');
  get diagnostics claimed = row_count;
  return claimed;
end;
$$;
revoke all on function public.claim_webhook_event(text, text, text) from public;
grant execute on function public.claim_webhook_event(text, text, text) to service_role;
