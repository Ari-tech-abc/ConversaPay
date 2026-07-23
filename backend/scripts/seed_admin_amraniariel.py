"""
Seed / reset the fixed ConversaPay administrator: AMRANIARIEL.

The password is intentionally required from the environment. This script
must never create a usable account with a committed or implicit password.

Usage:
    ADMIN_SEED_PASSWORD='use-a-long-random-secret' \\
      python -m backend.scripts.seed_admin_amraniariel
"""

import hashlib
import os
import secrets
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from supabase import create_client
from backend.config import settings

ADMIN_USERNAME = "AMRANIARIEL"
ADMIN_EMAIL = os.environ.get("ADMIN_SEED_EMAIL", "amraniariel12@gmail.com")
ADMIN_FULL_NAME = "Ariel Amrani"


def hash_password(password: str) -> str:
    """Salted PBKDF2-SHA256 hash, matching the admin router format."""
    salt = secrets.token_hex(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${digest.hex()}"


def seed_admin() -> None:
    password = os.environ.get("ADMIN_SEED_PASSWORD")
    if not password or len(password) < 12:
        raise SystemExit("ADMIN_SEED_PASSWORD is required and must be at least 12 characters")

    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    existing = supabase.table("admin_users").select("id").eq("username", ADMIN_USERNAME).execute()
    if not existing.data:
        existing = supabase.table("admin_users").select("id").eq("email", ADMIN_EMAIL).execute()

    payload = {
        "username": ADMIN_USERNAME,
        "email": ADMIN_EMAIL,
        "full_name": ADMIN_FULL_NAME,
        "password_hash": hash_password(password),
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
        supabase.table("admin_users").update(payload).eq("id", existing.data[0]["id"]).execute()
        print("Updated existing admin and reset password.")
    else:
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
        supabase.table("admin_users").insert(payload).execute()
        print("Created new admin.")

    print(f"Username: {ADMIN_USERNAME}")
    print(f"Email: {ADMIN_EMAIL}")
    print("Password: supplied via ADMIN_SEED_PASSWORD and never printed")


if __name__ == "__main__":
    seed_admin()
