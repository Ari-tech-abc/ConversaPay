-- Keep the businesses tier constraint aligned with the application plan model.
-- Safe additive repair: no rows are deleted or rewritten.

ALTER TABLE businesses
    DROP CONSTRAINT IF EXISTS businesses_subscription_tier_check;

ALTER TABLE businesses
    ADD CONSTRAINT businesses_subscription_tier_check
    CHECK (subscription_tier IN ('free', 'pro', 'premium'));
