-- ============================================
-- Migration: webhook_events (atomic webhook idempotency)
-- Fix H4: replaces the overwrite-prone profiles.payme_sale_id idempotency
-- check with a durable, append-only ledger. The UNIQUE(provider, event_id)
-- constraint guarantees each provider event is processed exactly once, even
-- under concurrent delivery, because the first INSERT wins and any duplicate
-- raises a unique violation the application treats as "already processed".
-- Safe to run against an existing database.
-- ============================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS webhook_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider VARCHAR(50) NOT NULL,
    event_id VARCHAR(255) NOT NULL,
    status VARCHAR(50),
    received_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    UNIQUE (provider, event_id)
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_provider_event
    ON webhook_events(provider, event_id);

-- Backend-only table: accessed exclusively via the service role.
ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;

GRANT ALL ON webhook_events TO service_role;
