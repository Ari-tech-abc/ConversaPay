"""
Execute database migration for email verification fields.
This script connects directly to Supabase PostgreSQL and executes the migration.
"""
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Extract database connection details from Supabase URL
# Format: https://[project-id].supabase.co
if SUPABASE_URL:
    project_id = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
    DB_HOST = f"db.{project_id}.supabase.co"
    DB_PORT = 5432
    DB_NAME = "postgres"
    DB_USER = "postgres"
else:
    DB_HOST = DB_NAME = DB_USER = None

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

def get_db_password():
    """Prompt user for database password."""
    print("\n[SECURITY] Database Password Required")
    print("=" * 80)
    print("To execute the migration, we need your Supabase database password.")
    print("You can find this in:")
    print("  1. Supabase Dashboard -> Settings -> Database")
    print("  2. Look for 'Connection string' or 'Database password'")
    print("  3. The password is set during project creation")
    print("=" * 80)
    
    # Try to get from environment first
    db_password = os.getenv("SUPABASE_DB_PASSWORD")
    if db_password:
        print("[OK] Found SUPABASE_DB_PASSWORD in environment")
        return db_password
    
    # Prompt user
    import getpass
    db_password = getpass.getpass("\nEnter your Supabase database password: ")
    return db_password

def execute_migration_with_psycopg2():
    """Execute migration using psycopg2."""
    try:
        import psycopg2
        from psycopg2 import sql
        
        db_password = get_db_password()
        
        if not db_password:
            print("[ERROR] Database password is required")
            return False
        
        print(f"\n[CONNECT] Connecting to database: {DB_HOST}:{DB_PORT}/{DB_NAME}")
        
        # Connect to database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=db_password,
            connect_timeout=10
        )
        
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("[OK] Connected successfully!")
        print("\n[EXECUTE] Executing migration...")
        print("=" * 80)
        
        # Execute migration
        cursor.execute(MIGRATION_SQL)
        
        print("[OK] Migration executed successfully!")
        print("\n[VERIFY] Verifying changes...")
        
        # Verify columns were added
        cursor.execute("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = 'profiles'
            AND column_name IN ('email_verified', 'email_verification_token', 'email_verification_expires_at')
            ORDER BY column_name;
        """)
        
        columns = cursor.fetchall()
        
        if columns:
            print("\n[OK] Verified - New columns found:")
            for col in columns:
                print(f"   - {col[0]} ({col[1]})")
        else:
            print("[WARNING] Could not verify columns were added")
        
        # Verify indexes were created
        cursor.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'profiles'
            AND indexname IN ('idx_profiles_email_verified', 'idx_profiles_email_verification_token');
        """)
        
        indexes = cursor.fetchall()
        
        if indexes:
            print("\n[OK] Verified - Indexes created:")
            for idx in indexes:
                print(f"   - {idx[0]}")
        else:
            print("[WARNING] Could not verify indexes were created")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 80)
        print("[SUCCESS] Database migration completed successfully!")
        print("=" * 80)
        
        return True
        
    except ImportError:
        print("[WARNING] psycopg2 not installed. Attempting to install...")
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
            print("[OK] psycopg2-binary installed. Please run the migration again.")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to install psycopg2: {str(e)}")
            return False
    except Exception as e:
        print(f"[ERROR] Migration failed: {str(e)}")
        return False

def execute_migration_with_asyncpg():
    """Execute migration using asyncpg."""
    try:
        import asyncio
        import asyncpg
        
        async def run_async_migration():
            db_password = get_db_password()
            
            if not db_password:
                print("[ERROR] Database password is required")
                return False
            
            print(f"\n[CONNECT] Connecting to database: {DB_HOST}:{DB_PORT}/{DB_NAME}")
            
            # Connect to database
            conn = await asyncpg.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=db_password,
                timeout=10
            )
            
            print("[OK] Connected successfully!")
            print("\n[EXECUTE] Executing migration...")
            print("=" * 80)
            
            # Execute migration
            await conn.execute(MIGRATION_SQL)
            
            print("[OK] Migration executed successfully!")
            print("\n[VERIFY] Verifying changes...")
            
            # Verify columns
            columns = await conn.fetch("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'profiles'
                AND column_name IN ('email_verified', 'email_verification_token', 'email_verification_expires_at')
                ORDER BY column_name;
            """)
            
            if columns:
                print("\n[OK] Verified - New columns found:")
                for col in columns:
                    print(f"   - {col['column_name']} ({col['data_type']})")
            
            # Verify indexes
            indexes = await conn.fetch("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'profiles'
                AND indexname IN ('idx_profiles_email_verified', 'idx_profiles_email_verification_token');
            """)
            
            if indexes:
                print("\n[OK] Verified - Indexes created:")
                for idx in indexes:
                    print(f"   - {idx['indexname']}")
            
            await conn.close()
            
            print("\n" + "=" * 80)
            print("[SUCCESS] Database migration completed successfully!")
            print("=" * 80)
            
            return True
        
        return asyncio.run(run_async_migration())
        
    except ImportError:
        print("[WARNING] asyncpg not installed. Attempting to install...")
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "asyncpg"])
            print("[OK] asyncpg installed. Please run the migration again.")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to install asyncpg: {str(e)}")
            return False
    except Exception as e:
        print(f"[ERROR] Migration failed: {str(e)}")
        return False

def show_manual_instructions():
    """Show manual migration instructions."""
    print("\n" + "=" * 80)
    print("[MANUAL] MANUAL MIGRATION INSTRUCTIONS")
    print("=" * 80)
    print("\nIf automatic migration fails, please execute the SQL manually:")
    print("\n1. Go to: https://supabase.com/dashboard")
    print("2. Select your project: uldbxzarukmrpujayigg")
    print("3. Navigate to: SQL Editor (left sidebar)")
    print("4. Click: 'New query'")
    print("5. Paste the following SQL:")
    print("\n" + "-" * 80)
    print(MIGRATION_SQL)
    print("-" * 80)
    print("\n6. Click: 'Run' (or press Ctrl+Enter)")
    print("7. Verify: You should see 'Success. No rows returned'")
    print("\n" + "=" * 80)

def main():
    """Main migration function."""
    print("=" * 80)
    print("[DATABASE] ConversaPay - Email Verification Database Migration")
    print("=" * 80)
    print(f"[LOCATION] Database: {DB_HOST}")
    print(f"[TASK] Migration: Add email verification fields to profiles table")
    print("=" * 80)
    
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("[ERROR] SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        return False
    
    # Try psycopg2 first (synchronous)
    try:
        import psycopg2
        print("[OK] psycopg2 found, using synchronous connection")
        success = execute_migration_with_psycopg2()
        if success:
            return True
    except ImportError:
        pass
    
    # Try asyncpg (asynchronous)
    try:
        import asyncpg
        print("[OK] asyncpg found, using asynchronous connection")
        success = execute_migration_with_asyncpg()
        if success:
            return True
    except ImportError:
        pass
    
    # Neither available, show manual instructions
    print("[WARNING] No PostgreSQL driver found (psycopg2 or asyncpg)")
    show_manual_instructions()
    
    # Ask if user wants to install psycopg2
    try:
        response = input("\nWould you like to install psycopg2-binary now? (y/n): ").strip().lower()
        if response == 'y':
            import subprocess
            print("\n[INSTALL] Installing psycopg2-binary...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
            print("[OK] psycopg2-binary installed successfully!")
            print("[ACTION] Please run this script again to execute the migration.")
            return False
    except Exception as e:
        print(f"[ERROR] Installation failed: {str(e)}")
    
    return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[WARNING] Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)