-- Safe, additive SaaS hardening migration.
-- This migration does not drop tables, delete data, or seed credentials.

ALTER TABLE admin_users
    ADD COLUMN IF NOT EXISTS username TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS admin_users_username_lower_key
    ON admin_users (LOWER(username))
    WHERE username IS NOT NULL;

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

ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
GRANT ALL ON webhook_events TO service_role;

ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMP WITH TIME ZONE;
