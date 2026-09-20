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
    claimed boolean := false;
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
    on conflict (provider, provider_event_id) do update
        set processing_status = case
            when payment_webhook_events.processing_status = 'failed'
                 and payment_webhook_events.updated_at < now() - interval '5 minutes'
            then 'processing'
            else payment_webhook_events.processing_status
        end,
        error_message = case
            when payment_webhook_events.processing_status = 'failed'
                 and payment_webhook_events.updated_at < now() - interval '5 minutes'
            then null
            else payment_webhook_events.error_message
        end
    returning processing_status = 'processing' into claimed;

    return coalesce(claimed, false);
end;
$$;

create or replace function public.mark_webhook_processed(p_event_id text)
returns void
language sql
security definer
set search_path = public
as $$
    update public.payment_webhook_events
       set processing_status = 'processed',
           processed_at = now(),
           error_message = null
     where provider_event_id = p_event_id;
$$;

create or replace function public.mark_webhook_failed(p_event_id text, p_error_message text)
returns void
language sql
security definer
set search_path = public
as $$
    update public.payment_webhook_events
       set processing_status = 'failed',
           error_message = left(coalesce(p_error_message, 'Unknown webhook error'), 2000)
     where provider_event_id = p_event_id;
$$;

revoke all on function public.claim_webhook_event(text, text, text) from public;
grant execute on function public.claim_webhook_event(text, text, text) to service_role;

revoke all on function public.mark_webhook_processed(text) from public;
grant execute on function public.mark_webhook_processed(text) to service_role;

revoke all on function public.mark_webhook_failed(text, text) from public;
grant execute on function public.mark_webhook_failed(text, text) to service_role;
