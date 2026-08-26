-- ============================================
-- ConversaPay - Email Verification Migration
-- ============================================
-- Execute this SQL in Supabase Dashboard -> SQL Editor
-- ============================================

-- Add email verification fields to profiles table
ALTER TABLE profiles 
ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR(255),
ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMP WITH TIME ZONE;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_profiles_email_verified ON profiles(email_verified);
CREATE INDEX IF NOT EXISTS idx_profiles_email_verification_token ON profiles(email_verification_token);

-- Verify the changes
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'profiles' 
AND column_name IN ('email_verified', 'email_verification_token', 'email_verification_expires_at')
ORDER BY column_name;

-- Verify indexes
SELECT 
    indexname, 
    tablename 
FROM pg_indexes 
WHERE tablename = 'profiles' 
AND indexname IN ('idx_profiles_email_verified', 'idx_profiles_email_verification_token');

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Email verification migration completed successfully!';
    RAISE NOTICE 'New columns added: email_verified, email_verification_token, email_verification_expires_at';
    RAISE NOTICE 'Indexes created: idx_profiles_email_verified, idx_profiles_email_verification_token';
END $$;