"""Read-only preflight. Does not contact a payment provider or create a charge."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from backend.config import settings
    from supabase import create_client
    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    checks = {}
    for table, fields in {
        'profiles': 'user_id,subscription_provider,provider_subscription_id,subscription_sync_checked_at',
        'subscription_checkout_attempts': 'id,status',
        'subscription_cancellations': 'id,status',
        'subscription_invoices': 'id,status',
        'subscription_plan_requests': 'id,status',
        'subscription_operational_alerts': 'alert_key,kind,resolved_at',
    }.items():
        try:
            db.table(table).select(fields).limit(1).execute()
            checks[table] = 'available'
        except Exception:
            checks[table] = 'unavailable'
    try:
        result = db.rpc('subscription_storage_ready', {}).execute().data
        checks['management_rpc'] = 'available' if isinstance(result, dict) and result.get('ready') is True else 'unavailable'
    except Exception:
        checks['management_rpc'] = 'unavailable'
    print(json.dumps({'storage': checks, 'worker_enabled': settings.SUBSCRIPTION_WORKER_ENABLED, 'provider': settings.SUBSCRIPTION_PROVIDER}))
    return 0 if all(value == 'available' for value in checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
