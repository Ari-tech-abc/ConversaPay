"""
Seed / reset the fixed ConversaPay administrator: AMRANIARIEL.

Why this exists
---------------
The admin credentials must NEVER live in front-end HTML/JS (anyone could read
them via "view source"). Instead the account lives in the ``admin_users`` table
with a salted PBKDF2 password hash, exactly like the interactive creation
script. The password is therefore CHANGEABLE at any time - just re-run this
script (or update the row in the database) with a new value.

Usage
-----
    # 1. Make sure the username column exists (once):
    #    psql < backend/scripts/add_admin_username.sql
    #
    # 2. Seed / reset the admin:
    python -m backend.scripts.seed_admin_amraniariel

The password can be overridden with the ADMIN_SEED_PASSWORD env var so it does
not have to be committed anywhere.
"""

import os
import sys
import hashlib
import secrets
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from supabase import create_client
from backend.config import settings

# --- Fixed identity -------------------------------------------------------
ADMIN_USERNAME = "AMRANIARIEL"
ADMIN_EMAIL = os.environ.get("ADMIN_SEED_EMAIL", "amraniariel12@gmail.com")
ADMIN_FULL_NAME = "Ariel Amrani"
# Default password is changeable: override via env, or change the DB row later.
ADMIN_PASSWORD = os.environ.get("ADMIN_SEED_PASSWORD", "AA13243546")


def hash_password(password: str) -> str:
    """Salted PBKDF2-SHA256 hash, matching the format used by the admin router."""
    salt = secrets.token_hex(32)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${pwd_hash.hex()}"


def seed_admin() -> None:
    print("=" * 60)
    print("ConversaPay - seeding fixed admin:", ADMIN_USERNAME)
    print("=" * 60)

    supabase = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )

    password_hash = hash_password(ADMIN_PASSWORD)
    now = datetime.now(timezone.utc).isoformat()

    # Look up an existing row by username first, then by email.
    existing = supabase.table("admin_users").select("id").eq("username", ADMIN_USERNAME).execute()
    if not existing.data:
        existing = supabase.table("admin_users").select("id").eq("email", ADMIN_EMAIL).execute()

    payload = {
        "username": ADMIN_USERNAME,
        "email": ADMIN_EMAIL,
        "full_name": ADMIN_FULL_NAME,
        "password_hash": password_hash,
        "role": "super_admin",
        "status": "active",
        "login_attempts": 0,
        "locked_until": None,
        "permissions": {
            "manage_domains": True,
            "manage_abuse_reports": True,
            "view_analytics": True,
            "manage_admins": True,
        },
    }

    if existing.data:
        admin_id = existing.data[0]["id"]
        supabase.table("admin_users").update(payload).eq("id", admin_id).execute()
        print("Updated existing admin and reset password.")
    else:
        payload["created_at"] = now
        supabase.table("admin_users").insert(payload).execute()
        print("Created new admin.")

    print(f"   Username: {ADMIN_USERNAME}")
    print(f"   Email:    {ADMIN_EMAIL}")
    print("   Role:     super_admin")
    print("   Password: (set - change it any time by re-running with ADMIN_SEED_PASSWORD)")
    print("\nLog in at: /admin-login.html  (use the username)")


if __name__ == "__main__":
    seed_admin()
