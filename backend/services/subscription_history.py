"""Store only verified invoice summaries; never expose provider payloads."""
from backend.services.subscription_catalog import PLANS, paid_subscription_period
from backend.services.subscription_checkout import billing_rpc


def record_invoice(db, user_id, subscription, plan_key):
    invoice = subscription.get('latest_invoice')
    if not isinstance(invoice, dict) or not invoice.get('id'):
        return
    parent = (invoice.get('parent') or {}).get('subscription_details') or {}
    bound = invoice.get('subscription') or parent.get('subscription')
    bound = bound.get('id') if isinstance(bound, dict) else bound
    if bound != subscription.get('id'):
        raise ValueError('billing_invoice_mismatch')
    plan = PLANS.get(plan_key)
    period = paid_subscription_period(subscription, plan) if plan else None
    if period:
        state, amount = 'paid', invoice.get('amount_paid')
    elif invoice.get('status') in {'open', 'uncollectible'} and invoice.get('attempted') is True:
        state, amount = 'failed', invoice.get('amount_due')
    else:
        return
    if type(amount) is not int or amount < 0 or str(invoice.get('currency', '')).upper() != 'ILS':
        raise ValueError('billing_invoice_amount_invalid')
    from backend.services.subscription_service import period_end_iso
    occurred = period_end_iso(invoice.get('created'))
    if not occurred:
        raise ValueError('billing_invoice_date_missing')
    billing_rpc(db, 'record_subscription_invoice', {
        'p_user_id': user_id, 'p_provider': 'stripe', 'p_subscription_id': subscription['id'],
        'p_invoice_id': invoice['id'], 'p_status': state, 'p_amount': amount, 'p_currency': 'ILS',
        'p_start': period_end_iso(period[0]) if period else None,
        'p_end': period_end_iso(period[1]) if period else None, 'p_occurred': occurred,
    })
