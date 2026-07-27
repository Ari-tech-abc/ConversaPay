-- Phase 3 billing foundations. Additive and replay-safe.
CREATE TABLE IF NOT EXISTS public.usage_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  metric text NOT NULL,
  quantity integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
  source text NOT NULL,
  source_event_id text,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (business_id, metric, source, source_event_id)
);
CREATE INDEX IF NOT EXISTS usage_events_business_metric_idx ON public.usage_events(business_id, metric, occurred_at DESC);
CREATE TABLE IF NOT EXISTS public.billing_reconciliation_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  status text NOT NULL DEFAULT 'running',
  scanned_count integer NOT NULL DEFAULT 0,
  drift_count integer NOT NULL DEFAULT 0,
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);
ALTER TABLE public.usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_reconciliation_runs ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.usage_events TO service_role;
GRANT ALL ON public.billing_reconciliation_runs TO service_role;
