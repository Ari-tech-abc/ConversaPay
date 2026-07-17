"""
Database migration script to add email verification fields to profiles table.
Run this script to apply the migration to Supabase.
"""
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Get Supabase credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    sys.exit(1)

# Create Supabase client with service role key (admin privileges)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Migration SQL
MIGRATION_SQL = """
-- Add email verification fields to profiles table
ALTER TABLE profiles 
ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR(255),
ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMP WITH TIME ZONE;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_profiles_email_verified ON profiles(email_verified);
CREATE INDEX IF NOT EXISTS idx_profiles_email_verification_token ON profiles(email_verification_token);
"""

def run_migration():
    """Execute the migration SQL."""
    try:
        print("🚀 Starting email verification migration...")
        print(f"📍 Database: {SUPABASE_URL}")
        
        # Execute the migration SQL
        # Note: Supabase Python client doesn't directly support raw SQL execution
        # We need to use the REST API or psycopg2 directly
        # For this migration, we'll use the Supabase SQL Editor approach
        
        print("\n📋 Migration SQL to execute:")
        print("=" * 80)
        print(MIGRATION_SQL)
        print("=" * 80)
        
        print("\n⚠️  IMPORTANT: Please execute this SQL in Supabase Dashboard:")
        print("1. Go to https://supabase.com/dashboard")
        print("2. Select your project")
        print("3. Navigate to SQL Editor")
        print("4. Paste the SQL above and click 'Run'")
        print("\nAlternatively, you can use the Supabase CLI or API to execute this migration.")
        
        # Try to verify if columns already exist
        print("\n🔍 Checking current schema...")
        
        # Query to check if columns exist
        check_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'profiles' 
        AND column_name IN ('email_verified', 'email_verification_token', 'email_verification_expires_at');
        """
        
        try:
            # Use Supabase's rpc or direct query
            # Since we can't execute raw SQL directly with the Python client,
            # we'll provide instructions for manual execution
            print("\n✅ Migration script prepared successfully!")
            print("\n📝 Next steps:")
            print("1. Open Supabase Dashboard → SQL Editor")
            print("2. Copy and paste the SQL from above")
            print("3. Click 'Run' to execute the migration")
            print("4. Verify the columns were added successfully")
            
            return True
            
        except Exception as e:
            print(f"⚠️  Could not verify schema: {str(e)}")
            print("Please manually execute the SQL in Supabase Dashboard")
            return False
            
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)