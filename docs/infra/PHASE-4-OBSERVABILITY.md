# Phase 4: Observability and Monitoring

Status: Draft

## Scope

- Standardize structured logs across FastAPI routers and service integrations.
- Add correlation IDs that propagate through frontend requests, webhooks, WhatsApp, Gemini, Stripe, and PayMe flows.
- Add production-safe health and readiness checks with dependency visibility.
- Add error tracking with Sentry or an equivalent provider, excluding secrets and payment details.
- Define uptime, latency, error-rate, webhook-failure, and billing-drift alerts.

## Acceptance criteria

- A single request can be traced across its major external calls.
- Health checks distinguish process health from dependency readiness.
- Errors are searchable with route, tenant-safe context, and correlation ID.
- Logs never contain access tokens, card data, webhook secrets, or API keys.
