-- Add payment_link to products
-- Run this in Supabase SQL Editor
ALTER TABLE products ADD COLUMN IF NOT EXISTS payment_link TEXT;
