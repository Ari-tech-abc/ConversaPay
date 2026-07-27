# Phase 3: Billing and Subscription Reconciliation

Status: Draft

## Scope

- Reconcile profile subscription state with Stripe events and stored subscription dates.
- Add usage metering foundations for messages, orders, and other billable units.
- Define dunning behavior for failed payments, retries, customer notices, and grace periods.
- Make subscription and payment webhooks idempotent and replay-safe.
- Add a reconciliation path for drift between Stripe and Supabase.

## Acceptance criteria

- Subscription state is derived from verified provider events, not client input.
- Duplicate or out-of-order events do not downgrade or double-charge an account.
- Failed billing has a documented retry and notification lifecycle.
- An operator can identify and repair billing drift safely.
