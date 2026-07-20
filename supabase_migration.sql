-- ============================================
-- Supabase Migration: Add Missing Columns
-- Safe migration for production database
-- Run this in Supabase Dashboard > SQL Editor
-- ============================================
-- This adds missing columns without dropping tables
-- ============================================

-- ============================================
-- 1. Add missing columns to businesses table
-- ============================================

-- Add bot_name column for AI chatbot customization
ALTER TABLE businesses 
ADD COLUMN IF NOT EXISTS bot_name VARCHAR(255);

-- Add greeting_message column for custom welcome messages
ALTER TABLE businesses 
ADD COLUMN IF NOT EXISTS greeting_message TEXT;

-- Add theme_colors column for UI customization
ALTER TABLE businesses 
ADD COLUMN IF NOT EXISTS theme_colors JSONB DEFAULT '{}';

-- Add comment to document the new columns
COMMENT ON COLUMN businesses.bot_name IS 'Custom name for the AI chatbot';
COMMENT ON COLUMN businesses.greeting_message IS 'Custom greeting message shown to visitors';
COMMENT ON COLUMN businesses.theme_colors IS 'JSON object containing theme color configuration';

-- ============================================
-- 2. Verify profiles table has plan_type column
-- ============================================

-- Add plan_type column if it doesn't exist (should already exist)
ALTER TABLE profiles 
ADD COLUMN IF NOT EXISTS plan_type VARCHAR(50) DEFAULT 'free' CHECK (plan_type IN ('free', 'pro', 'premium'));

-- Add comment
COMMENT ON COLUMN profiles.plan_type IS 'User subscription plan type: free, pro, or premium';

-- ============================================
-- 3. Create indexes for new columns
-- ============================================

-- Index for bot_name (useful for filtering/searching)
CREATE INDEX IF NOT EXISTS idx_businesses_bot_name ON businesses(bot_name);

-- Index for plan_type in profiles (if not already exists)
CREATE INDEX IF NOT EXISTS idx_profiles_plan_type ON profiles(plan_type);

-- ============================================
-- 4. Update existing records with default values
-- ============================================

-- Set default bot_name to business_name for existing records
UPDATE businesses 
SET bot_name = business_name 
WHERE bot_name IS NULL;

-- Set default greeting_message for existing records
UPDATE businesses 
SET greeting_message = 'Hello! How can I help you today?' 
WHERE greeting_message IS NULL;

-- Set default plan_type for existing profiles
UPDATE profiles 
SET plan_type = 'free' 
WHERE plan_type IS NULL;

-- ============================================
-- 5. Verify the changes
-- ============================================

-- Check businesses table structure
SELECT 
    column_name, 
    data_type, 
    is_nullable, 
    column_default
FROM information_schema.columns
WHERE table_name = 'businesses'
AND column_name IN ('bot_name', 'greeting_message', 'theme_colors', 'settings')
ORDER BY ordinal_position;

-- Check profiles table structure
SELECT 
    column_name, 
    data_type, 
    is_nullable, 
    column_default
FROM information_schema.columns
WHERE table_name = 'profiles'
AND column_name = 'plan_type';

-- ============================================
-- Migration Complete
-- ============================================
-- All missing columns have been added safely
-- No data was deleted
-- ============================================