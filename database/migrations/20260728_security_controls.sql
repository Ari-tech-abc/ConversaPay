-- Phase 1 security controls. Additive and safe to run repeatedly.
ALTER TABLE public.webhook_events
  ADD COLUMN IF NOT EXISTS payload_hash text,
  ADD COLUMN IF NOT EXISTS processed_at timestamptz,
  ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS webhook_events_received_at_idx
  ON public.webhook_events(provider, received_at DESC);

CREATE INDEX IF NOT EXISTS webhook_events_payload_hash_idx
  ON public.webhook_events(provider, payload_hash);
