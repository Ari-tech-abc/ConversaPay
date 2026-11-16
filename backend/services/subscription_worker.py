"""Bounded recovery loop: reads provider state and repairs storage, never charges."""
import asyncio
import logging
from datetime import datetime, timezone
from backend.services.subscription_checkout import billing_rpc
from backend.services.subscription_gateway import get_subscription_gateway
from backend.services.subscription_reconciliation import reconcile_pending
from backend.services.subscription_catalog import invoice_confirms_subscription, PLANS
from backend.services.subscription_service import apply_subscription_state, period_end_iso, subscription_period_end

logger = logging.getLogger(__name__)


def run_cycle(db, limit=25):
    if not 1 <= limit <= 100:
        raise ValueError('limit must be between 1 and 100')
    report = reconcile_pending(db, limit, apply=True)
    rows = db.table('profiles').select('user_id,subscription_provider,provider_subscription_id').not_.is_('provider_subscription_id', 'null').order('subscription_sync_checked_at', nullsfirst=True).order('user_id').limit(limit).execute().data or []
    report['subscriptions_checked'] = len(rows)
    report['subscription_errors'] = 0
    for row in rows:
        try:
            provider = row.get('subscription_provider') or 'stripe'
            gateway = get_subscription_gateway(provider)
            gateway.ensure_ready()
            snapshot = gateway.retrieve_subscription(row['provider_subscription_id'])
            if snapshot.get('id') != row['provider_subscription_id']:
                raise ValueError('billing_subscription_mismatch')
            metadata = snapshot.get('metadata') or {}
            if metadata.get('user_id') != row['user_id']:
                raise ValueError('billing_owner_mismatch')
            plan = PLANS.get(metadata.get('plan_type'))
            if not plan:
                raise ValueError('billing_plan_unknown')
            applied = apply_subscription_state(user_id=row['user_id'], plan_type=plan.key,
                subscription_status=snapshot.get('status'), subscription_expires_at=period_end_iso(subscription_period_end(snapshot)),
                stripe_subscription_id=snapshot['id'], customer_id=snapshot.get('customer'), stripe_subscription=snapshot,
                cancel_at_period_end=bool(snapshot.get('cancel_at_period_end')),
                payment_confirmed=invoice_confirms_subscription(snapshot, plan), db=db)
            if not applied:
                raise ValueError('billing_snapshot_conflict')
            db.table('subscription_operational_alerts').update({'resolved_at': datetime.now(timezone.utc).isoformat()}).eq('alert_key', 'sync_failure:' + row['user_id']).execute()
        except Exception as exc:
            report['subscription_errors'] += 1
            logger.warning('Subscription sync failed for %s (%s)', row['user_id'], type(exc).__name__)
            db.table('subscription_operational_alerts').upsert({'alert_key': 'sync_failure:' + row['user_id'], 'kind': 'sync_failure', 'operation_id': row['user_id'], 'last_seen_at': datetime.now(timezone.utc).isoformat(), 'resolved_at': None}, on_conflict='alert_key').execute()
        finally:
            db.table('profiles').update({'subscription_sync_checked_at': datetime.now(timezone.utc).isoformat()}).eq('user_id', row['user_id']).execute()
    report.update(billing_rpc(db, 'scan_subscription_operations', {}))
    if report.get('open_alerts') or report['subscription_errors'] or report['needs_review']:
        logger.error('Billing operations require review: alerts=%s sync_errors=%s ambiguous=%s', report.get('open_alerts', 0), report['subscription_errors'], len(report['needs_review']))
    return report


async def run_subscription_worker(db, interval=300):
    while True:
        try:
            await asyncio.to_thread(run_cycle, db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error('Subscription worker unavailable (%s)', type(exc).__name__)
        await asyncio.sleep(interval)
