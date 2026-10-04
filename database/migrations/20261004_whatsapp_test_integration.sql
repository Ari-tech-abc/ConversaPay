-- Test-only Cloud API connection and durable inbox. Only the backend may access these.
CREATE TABLE IF NOT EXISTS public.whatsapp_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL UNIQUE REFERENCES public.businesses(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    phone_number_id TEXT NOT NULL UNIQUE,
    display_phone_number TEXT,
    access_token_encrypted TEXT NOT NULL,
    verify_token_encrypted TEXT NOT NULL,
    revision UUID NOT NULL DEFAULT gen_random_uuid(),
    test_recipients TEXT[] NOT NULL CHECK (cardinality(test_recipients) BETWEEN 1 AND 5),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    verified_at TIMESTAMPTZ,
    last_inbound_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.whatsapp_inbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence BIGINT GENERATED ALWAYS AS IDENTITY,
    connection_id UUID NOT NULL REFERENCES public.whatsapp_connections(id) ON DELETE CASCADE,
    revision UUID NOT NULL,
    meta_message_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    message_type TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    message_timestamp TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','sending','accepted','sent','delivered','read','failed','unknown','ignored')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    outbound_message_id TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (connection_id, meta_message_id)
);
CREATE INDEX IF NOT EXISTS whatsapp_inbox_work_idx ON public.whatsapp_inbox(status,next_attempt_at,sequence);
CREATE INDEX IF NOT EXISTS whatsapp_inbox_outbound_idx ON public.whatsapp_inbox(connection_id,outbound_message_id);
-- Receipts may arrive before the HTTP send response is committed to the inbox.
CREATE TABLE IF NOT EXISTS public.whatsapp_delivery_receipts (
    connection_id UUID NOT NULL REFERENCES public.whatsapp_connections(id) ON DELETE CASCADE,
    outbound_message_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('sent','delivered','read','failed')),
    error_code TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (connection_id,outbound_message_id)
);
ALTER TABLE public.whatsapp_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.whatsapp_inbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.whatsapp_delivery_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.whatsapp_connections, public.whatsapp_inbox, public.whatsapp_delivery_receipts FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.whatsapp_connections, public.whatsapp_inbox, public.whatsapp_delivery_receipts TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.whatsapp_inbox_sequence_seq TO service_role;

CREATE OR REPLACE FUNCTION public.claim_whatsapp_message() RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE job public.whatsapp_inbox;
BEGIN
    -- A timed-out send may already have reached Meta. Never automatically resend it.
    UPDATE public.whatsapp_inbox SET status='unknown',error_code='delivery_unknown',updated_at=now()
    WHERE status='sending' AND lease_until < now();
    DELETE FROM public.whatsapp_inbox WHERE created_at < now()-interval '30 days';
    DELETE FROM public.whatsapp_delivery_receipts WHERE updated_at < now()-interval '30 days';
    SELECT m.* INTO job FROM public.whatsapp_inbox m
    WHERE ((m.status='pending' AND m.next_attempt_at <= now()) OR (m.status='processing' AND m.lease_until < now()))
      AND NOT EXISTS (SELECT 1 FROM public.whatsapp_inbox earlier
          WHERE earlier.connection_id=m.connection_id AND earlier.sender=m.sender
          AND earlier.sequence<m.sequence AND earlier.status IN ('pending','processing','sending'))
    ORDER BY m.sequence FOR UPDATE SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN NULL; END IF;
    UPDATE public.whatsapp_inbox SET status='processing',attempts=attempts+1,
        lease_token=gen_random_uuid(),lease_until=now()+interval '120 seconds',updated_at=now()
    WHERE id=job.id RETURNING * INTO job;
    RETURN to_jsonb(job);
END; $$;

CREATE OR REPLACE FUNCTION public.begin_whatsapp_send(p_id UUID,p_lease_token UUID) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    UPDATE public.whatsapp_inbox m SET status='sending',lease_until=now()+interval '120 seconds',updated_at=now()
    FROM public.whatsapp_connections c WHERE m.id=p_id AND m.lease_token=p_lease_token
      AND m.status='processing' AND m.lease_until>now() AND c.id=m.connection_id
      AND c.enabled AND c.verified_at IS NOT NULL AND c.revision=m.revision
      AND m.sender=ANY(c.test_recipients);
    RETURN FOUND;
END; $$;

CREATE OR REPLACE FUNCTION public.finish_whatsapp_message(p_id UUID,p_lease_token UUID,p_status TEXT,
    p_outbound_id TEXT DEFAULT NULL,p_error_code TEXT DEFAULT NULL) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE connection UUID;
BEGIN
    IF p_status NOT IN ('pending','accepted','failed','unknown','ignored') THEN RAISE EXCEPTION 'Invalid status'; END IF;
    IF p_status='accepted' AND p_outbound_id IS NOT NULL THEN
        SELECT connection_id INTO connection FROM public.whatsapp_inbox WHERE id=p_id;
        IF NOT FOUND THEN RETURN FALSE; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('whatsapp-receipt:'||connection::text||':'||p_outbound_id,0));
    END IF;
    UPDATE public.whatsapp_inbox m SET status=CASE WHEN p_status='accepted' THEN
          COALESCE((SELECT r.status FROM public.whatsapp_delivery_receipts r WHERE r.connection_id=m.connection_id
            AND r.outbound_message_id=p_outbound_id),p_status) ELSE p_status END,
        outbound_message_id=p_outbound_id,error_code=CASE WHEN p_status='accepted' THEN
          (SELECT r.error_code FROM public.whatsapp_delivery_receipts r WHERE r.connection_id=m.connection_id
            AND r.outbound_message_id=p_outbound_id) ELSE p_error_code END,
        next_attempt_at=now()+interval '30 seconds',lease_until=NULL,updated_at=now()
    WHERE id=p_id AND lease_token=p_lease_token AND status IN ('processing','sending','unknown')
      AND (p_status<>'pending' OR status='processing');
    RETURN FOUND;
END; $$;

CREATE OR REPLACE FUNCTION public.whatsapp_delivery_status(p_connection_id UUID,p_outbound_id TEXT,p_status TEXT,p_error_code TEXT DEFAULT NULL)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    IF p_status NOT IN ('sent','delivered','read','failed') THEN RETURN; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('whatsapp-receipt:'||p_connection_id::text||':'||p_outbound_id,0));
    INSERT INTO public.whatsapp_delivery_receipts(connection_id,outbound_message_id,status,error_code)
    VALUES(p_connection_id,p_outbound_id,p_status,p_error_code)
    ON CONFLICT (connection_id,outbound_message_id) DO UPDATE SET status=EXCLUDED.status,error_code=EXCLUDED.error_code,updated_at=now()
    WHERE (CASE whatsapp_delivery_receipts.status WHEN 'read' THEN 3 WHEN 'delivered' THEN 2 ELSE 1 END)
      < (CASE EXCLUDED.status WHEN 'read' THEN 3 WHEN 'delivered' THEN 2 ELSE 1 END)
      OR (EXCLUDED.status='failed' AND whatsapp_delivery_receipts.status='sent');
    UPDATE public.whatsapp_inbox SET status=p_status,error_code=p_error_code,updated_at=now()
    WHERE connection_id=p_connection_id AND outbound_message_id=p_outbound_id
      AND (CASE status WHEN 'read' THEN 3 WHEN 'delivered' THEN 2 WHEN 'sent' THEN 1 WHEN 'failed' THEN 1 ELSE 0 END)
        < (CASE p_status WHEN 'read' THEN 3 WHEN 'delivered' THEN 2 WHEN 'sent' THEN 1 WHEN 'failed' THEN 1 END)
      OR (connection_id=p_connection_id AND outbound_message_id=p_outbound_id AND status='sent' AND p_status='failed');
END; $$;
REVOKE ALL ON FUNCTION public.claim_whatsapp_message(), public.begin_whatsapp_send(UUID,UUID),
    public.finish_whatsapp_message(UUID,UUID,TEXT,TEXT,TEXT), public.whatsapp_delivery_status(UUID,TEXT,TEXT,TEXT) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_whatsapp_message(), public.begin_whatsapp_send(UUID,UUID),
    public.finish_whatsapp_message(UUID,UUID,TEXT,TEXT,TEXT), public.whatsapp_delivery_status(UUID,TEXT,TEXT,TEXT) TO service_role;
NOTIFY pgrst, 'reload schema';
