-- Idempotency functions for the payment_webhook_events table.
-- Apply after 20260920_payment_webhook_idempotency.sql.

create or replace function public.claim_webhook_event(
    p_provider text,
    p_event_id text,
    p_event_type text
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    inserted_id uuid;
    current_status text;
    current_updated_at timestamptz;
begin
    insert into public.payment_webhook_events (
        provider,
        provider_event_id,
        event_type,
        processing_status
    ) values (
        p_provider,
        p_event_id,
        p_event_type,
        'processing'
    )
    on conflict (provider, provider_event_id) do nothing
    returning id into inserted_id;

    if inserted_id is not null then
        return true;
    end if;

    select processing_status, updated_at
      into current_status, current_updated_at
      from public.payment_webhook_events
     where provider = p_provider
       and provider_event_id = p_event_id
     for update;

    if current_status = 'failed'
       and current_updated_at < now() - interval '5 minutes' then
        update public.payment_webhook_events
           set processing_status = 'processing',
               error_message = null,
               processed_at = null
         where provider = p_provider
           and provider_event_id = p_event_id;
        return true;
    end if;

    return false;
end;
$$;

drop function if exists public.mark_webhook_processed(text);
drop function if exists public.mark_webhook_failed(text, text);

create or replace function public.mark_webhook_processed(p_provider text, p_event_id text)
returns void
language sql
security definer
set search_path = public
as $$
    update public.payment_webhook_events
       set processing_status = 'processed',
           processed_at = now(),
           error_message = null
     where provider = p_provider
       and provider_event_id = p_event_id;
$$;

create or replace function public.mark_webhook_failed(p_provider text, p_event_id text, p_error_message text)
returns void
language sql
security definer
set search_path = public
as $$
    update public.payment_webhook_events
       set processing_status = 'failed',
           error_message = left(coalesce(p_error_message, 'Unknown webhook error'), 2000)
     where provider = p_provider
       and provider_event_id = p_event_id;
$;

revoke all on function public.claim_webhook_event(text, text, text) from public;
grant execute on function public.claim_webhook_event(text, text, text) to service_role;

revoke all on function public.mark_webhook_processed(text, text) from public;
grant execute on function public.mark_webhook_processed(text, text) to service_role;

revoke all on function public.mark_webhook_failed(text, text, text) from public;
grant execute on function public.mark_webhook_failed(text, text, text) to service_role;
