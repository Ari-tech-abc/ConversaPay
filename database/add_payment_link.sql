-- Safe additive migration for product payment links.
ALTER TABLE products ADD COLUMN IF NOT EXISTS payment_link TEXT;
