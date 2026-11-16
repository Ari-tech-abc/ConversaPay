"""Inspect pending subscription confirmations; --apply verifies and repairs them.

This command never creates a checkout or retries a card charge. Configure an
external schedule only after the provider and database migration are ready.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from backend.config import settings
    from backend.services.subscription_reconciliation import reconcile_pending
    from supabase import create_client
    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    print(json.dumps(reconcile_pending(db, args.limit, args.apply)))


if __name__ == "__main__":
    main()
