"""
Script to create the first admin user.
Run this once to set up your admin account.
"""

import os
import sys
import hashlib
import secrets
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supabase import create_client
from backend.config import settings

def hash_password(password: str) -> str:
    """Hash password with salt."""
    salt = secrets.token_hex(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${pwd_hash.hex()}"

def create_admin_user():
    """Create first admin user."""
    
    print("=" * 60)
    print("ConversaPay Admin User Creation")
    print("=" * 60)
    
    # Get input
    email = input("\nAdmin Email: ").strip()
    if not email:
        print("Email is required")
        return
    
    full_name = input("Full Name: ").strip()
    password = input("Password (min 8 chars): ").strip()
    
    if len(password) < 8:
        print("Password must be at least 8 characters")
        return
    
    # Confirm password
    password_confirm = input("Confirm Password: ").strip()
    if password != password_confirm:
        print("Passwords don't match")
        return
    
    # Connect to Supabase
    print("\nConnecting to database...")
    supabase = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )
    
    # Check if admin already exists
    existing = supabase.table("admin_users")\
        .select("id")\
        .eq("email", email)\
        .execute()
    
    if existing.data:
        print("Admin user with this email already exists")
        return
    
    # Hash password
    password_hash = hash_password(password)
    
    # Create admin user
    print("Creating admin user...")
    admin = supabase.table("admin_users")\
        .insert({
            "email": email,
            "password_hash": password_hash,
            "full_name": full_name,
            "role": "super_admin",
            "status": "active",
            "permissions": {
                "manage_domains": True,
                "manage_abuse_reports": True,
                "view_analytics": True,
                "manage_admins": True
            }
        })\
        .execute()
    
    if admin.data:
        print("\nAdmin user created successfully!")
        print(f"   Email: {email}")
        print(f"   Role: super_admin")
        print(f"   Status: active")
        print("\nAccess admin dashboard at: http://localhost:8000/admin")
    else:
        print("Failed to create admin user")

if __name__ == "__main__":
    create_admin_user()
