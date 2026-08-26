# Talk2Pay (ConversaPay)

Talk2Pay is a multi-tenant payment and conversational-commerce platform. It combines a FastAPI backend, a static frontend, Supabase/PostgreSQL persistence, pluggable payment providers (Stripe, PayMe, Cardcom), WhatsApp Cloud API integration, an embeddable widget, and a WordPress plugin.

## Contents

- [Architecture](#architecture)
- [Threat model and security](#threat-model-and-security)
- [Orders and payment lifecycle](#orders-and-payment-lifecycle)
- [Payment providers](#payment-providers)
- [Onboarding](#onboarding)
- [Local development](#local-development)
- [Environment variables](#environment-variables)
- [Testing](#testing)
- [CI/CD](#cicd)
- [Database and migrations](#database-and-migrations)
- [Repository layout](#repository-layout)

## Architecture

```text
Browser / Widget / WordPress plugin / WhatsApp
                    |
                    v
          FastAPI application (main.py)  v2.5.0
                    |
       routers -> services -> Supabase/PostgreSQL
                    |                 |
         Payment adapters       SQL migrations/RPCs
         (Stripe / PayMe)
                    |
              Stripe webhooks
```

### Application layers

- `main.py` is the FastAPI composition root (v2.5.0). It registers middleware, routers, health/readiness endpoints, and background migration startup.
- `backend/routers/` contains HTTP handlers for authentication, businesses, products, chat, orders, payments, analytics, dashboards, site builder, Stripe webhooks, WhatsApp, reconciliation, API keys, admin, onboarding, subscriptions, and widget.
- `backend/services/` contains integrations and domain services: Stripe, PayMe, Cardcom, Gemini AI, email, sessions, monitoring, subscriptions, migrations, reconciliation, billing, money helpers, product search, widget auth, and WhatsApp secret handling.
- `backend/middleware/` contains authentication, tenant ownership, rate limiting, correlation IDs, and request context behavior.
- `backend/models/schemas.py` contains Pydantic request and response models. Monetary fields use `Decimal`.
- `database/full_schema_bootstrap.sql` contains the idempotent baseline schema. Incremental SQL changes live under `database/migrations/`.
- `frontend/` contains the static application and widget assets. `wordpress-plugin/` contains the WordPress integration.
- `Site Builder/` contains the standalone site-builder sub-application.

The production API is mounted under `/api/v1`. FastAPI documentation is available locally when the environment is not production; production disables `/docs` and `/redoc`.

A `dev_simulator` router (`POST /api/v1/orders/{order_id}/mark-paid`) is included only in non-production environments for testing payment flows. It requires authentication and business ownership.

## Threat model and security

### Assets protected

- User identities, sessions, password-reset flows, and email-verification state.
- Tenant data: businesses, products, customers, conversations, orders, payments, logs, and API keys.
- Payment metadata and subscription state.
- WhatsApp access and verification credentials.
- Site-builder tokens and lead submissions.

### Trust boundaries

1. The browser, widget, WordPress plugin, WhatsApp, and payment providers are external callers.
2. FastAPI validates authentication, request shape, tenant ownership, rate limits, webhook signatures, and plan access.
3. Supabase/PostgreSQL is the persistence boundary and enforces RLS policies for authenticated access.
4. Service-role database access bypasses RLS, so server-side ownership checks remain mandatory.

### Controls implemented

- Supabase Auth bearer-token validation for protected routes.
- Tenant ownership checks through business ownership guards.
- PostgreSQL RLS policies for tenant-scoped tables.
- Stripe signature verification and webhook replay protection through `webhook_events`.
- HMAC verification for generic signed webhooks.
- Rate limiting for authentication, public order/chat flows, and site-builder lead submissions. A coarse IP-level safety-net middleware (`PublicEndpointSafetyNetMiddleware`, 120 req/min) backstops all public prefixes.
- Dual CORS middleware: wildcard for public endpoints, credentialed for configured origins.
- Security headers including CSP, HSTS in production, `X-Content-Type-Options`, `X-Frame-Options`, `Cross-Origin-Opener-Policy`, Referrer Policy, and Permissions Policy.
- API keys are stored as HMAC-SHA256 hashes; widget access is checked against the business scope. Origin/Referer headers are never used for security decisions.
- WhatsApp access and verification tokens are encrypted at rest; verification lookup uses an HMAC digest. Decrypted access tokens are used only inside the WhatsApp send path and are not returned by API responses.
- Service errors returned to clients are intentionally generic in sensitive paths.
- Dev-simulator endpoint is double-guarded: non-production flag plus authenticated business ownership.

### Operational assumptions

- `SECRET_KEY`, Supabase service credentials, Stripe secrets, Gemini credentials, email credentials, and production E2E secrets must be supplied through a secret manager or CI secret store, never committed to Git.
- The service-role key must never be sent to browsers or widgets.
- Production deployments must use HTTPS and keep `DEBUG=false`.

## Orders and payment lifecycle

### Public order creation

1. A client submits an order to `POST /api/v1/orders/pay`.
2. The backend resolves the business and loads active products by item key.
3. Prices come from the server-side catalog, not from client-supplied totals.
4. Product currencies must match and quantity is bounded.
5. Monetary calculations use `Decimal` via `backend/services/money.py` and are persisted as two-decimal values compatible with PostgreSQL `NUMERIC(12,2)`.
6. The order is stored as `pending` with `payment_status=pending`.

### Checkout

1. An authenticated owner calls `POST /api/v1/payments/checkout-session` for an order, or `POST /api/v1/payments/create-checkout-session` for a subscription.
2. The backend verifies business/order ownership and selects the active payment provider via `get_checkout_adapter()`.
3. The provider receives minor units derived from an exact decimal amount (e.g. cents for two-decimal currencies, agorot for ILS).
4. The payment row stores the provider session metadata and remains pending until the provider confirms the result.
5. The success page is informational only. It does not grant access or mark an order paid.

### Stripe webhook confirmation

```text
Stripe event
    -> signature verification
    -> claim_webhook_event(provider, event_id)
    -> event-specific handling
    -> update_order_payment_atomic(...)
    -> mark_webhook_processed(event_id)
```

For order payments, `backend/routers/stripe_webhook.py` calls the PostgreSQL RPC `update_order_payment_atomic`. The function updates the order and its latest payment inside one database transaction, locks the payment row, merges provider metadata, and sets `paid_at` for successful payments.

Duplicate Stripe events are rejected or safely reprocessed through the webhook claim table.

Subscription state is webhook-owned. `confirm-session` is read-only and does not mutate subscription state.

### Reconciliation

`POST /api/v1/reconciliation/orders` (authenticated, business-owner only) queries pending payments older than a configurable threshold and re-checks their status against Stripe. Stale paid or failed sessions are resolved via `update_order_payment_atomic`.

## Payment providers

The active provider is selected by the `PAYMENT_PROVIDER` environment variable (default: `stripe`). The `get_checkout_adapter()` factory in `backend/services/payment_adapters.py` returns the appropriate adapter.

| Provider | Adapter | Notes |
| --- | --- | --- |
| `stripe` | `StripeCheckoutAdapter` | Default. Stripe Checkout hosted page. |
| `payme` | `PayMeCheckoutAdapter` | PayMe IL hosted sale page. Requires `PAYME_CLIENT_KEY` and `PAYME_SELLER_PAYME_ID`. |
| `cardcom` | `CardcomService` (direct) | Cardcom v11 Low Profile. Requires `CARDCOM_TERMINAL_NUMBER`, `CARDCOM_USER_NAME`, optionally `CARDCOM_API_TOKEN`. |

## Onboarding

1. A user signs up through the authentication routes.
2. Supabase Auth creates the identity.
3. Talk2Pay creates a profile with free-plan defaults and an email-verification token.
4. The verification email is sent through the configured email provider (Resend).
5. The verification endpoint validates the token and marks the profile verified through a database RPC.
6. On the first successful login or OAuth finalization, the application ensures a profile and starter business exist.
7. The user creates products and configures the widget, WordPress plugin, or premium WhatsApp integration.
8. Premium users save WhatsApp settings through the authenticated settings endpoint. Sensitive credentials are encrypted before persistence.

## Local development

### Prerequisites

- Python 3.12 recommended.
- Node.js 20 for Playwright production E2E tests.
- A Supabase project and PostgreSQL connection string for readiness/migrations.
- Stripe test credentials for checkout and webhook development.

### Setup

```bash
git clone https://github.com/Ari-tech-abc/ConversaPay.git
cd ConversaPay
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with development credentials, then start the API:

```bash
uvicorn main:app --reload
```

Useful local endpoints:

- `GET /health`: fast liveness response (503 if migrations are pending/failed).
- `GET /ready`: database and optional Redis readiness checks.
- `GET /api/v1/config/public`: returns `supabase_url` and `supabase_anon_key` for frontend bootstrap.
- `GET /docs`: local OpenAPI UI when `ENVIRONMENT` is not `production`.
- `GET /redoc`: local ReDoc UI when `ENVIRONMENT` is not `production`.

The application starts database migration work in a background task so the liveness endpoint is not held behind the migration lock. Readiness should be used to decide whether the application is ready to serve dependency-backed traffic.

## Environment variables

The following settings are defined by `backend/config.py` or required by the CI workflows.

### Required application settings

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Application HMAC/encryption key material and security operations. |
| `SUPABASE_URL` | Supabase project URL. |
| `SUPABASE_ANON_KEY` | Public Supabase key used by client-side/auth operations. |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only Supabase service-role key. Never expose it publicly. |
| `GEMINI_API_KEY` | Gemini API credential for conversational responses. |
| `RESEND_API_KEY` | Email provider credential. |
| `EMAIL_FROM_ADDRESS` | Sender address for transactional email. |

### Database and runtime

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection used by readiness and migration runner. |
| `REDIS_URL` | Optional Redis URL for rate limiting/readiness. |
| `MIGRATIONS_AUTO_APPLY` | Enables automatic migration application during background startup. |
| `ENVIRONMENT` | Runtime environment: `development`, `test`, or `production`. |
| `DEBUG` | Debug flag; must be false in production. |
| `API_PREFIX` | API route prefix, default `/api/v1`. |
| `CORS_ORIGINS` | Comma-separated allowed origins. |
| `PAYMENT_PROVIDER` | Active payment provider: `stripe` (default), `payme`, or `cardcom`. |

### URLs and integrations

| Variable | Purpose |
| --- | --- |
| `BASE_URL` | Canonical application URL. |
| `FRONTEND_URL` | Frontend/widget URL. |
| `BACKEND_URL` | Backend URL. |
| `STRIPE_SECRET_KEY` | Server-only Stripe API key. |
| `STRIPE_WEBHOOK_SECRET` | Stripe signature verification secret. |
| `STRIPE_PRO_PRICE_ID` | Optional Stripe Price ID for the PRO plan. |
| `STRIPE_PREMIUM_PRICE_ID` | Optional Stripe Price ID for the PREMIUM plan. |
| `STRIPE_SUCCESS_URL` | Optional Stripe success URL override. |
| `STRIPE_CANCEL_URL` | Optional Stripe cancel URL override. |
| `PAYME_CLIENT_KEY` | PayMe client key. |
| `PAYME_SELLER_PAYME_ID` | PayMe seller ID. |
| `PAYME_API_BASE_URL` | PayMe API base URL (default: `https://sandbox.payme.io`). |
| `PAYME_GENERATE_PATH` | PayMe generate-sale path (default: `/api/generate-sale`). |
| `PAYME_SUCCESS_URL` | PayMe success redirect URL. |
| `PAYME_CANCEL_URL` | PayMe cancel redirect URL. |
| `PAYME_CALLBACK_URL` | Optional PayMe server callback URL. |
| `CARDCOM_TERMINAL_NUMBER` | Cardcom terminal number. |
| `CARDCOM_USER_NAME` | Cardcom username. |
| `CARDCOM_API_TOKEN` | Optional Cardcom Bearer token. |
| `CARDCOM_BASE_URL` | Cardcom API base URL (default: `https://cardcom.solutions`). |
| `CARDCOM_INDICATOR_URL` | Cardcom webhook callback URL. |
| `CARDCOM_SUCCESS_URL` | Cardcom success redirect URL. |
| `CARDCOM_FAILURE_URL` | Cardcom failure redirect URL. |
| `CARDCOM_CANCEL_URL` | Cardcom cancel redirect URL. |
| `META_APP_SECRET` | Meta/WhatsApp app secret. |
| `WHATSAPP_APP_SECRET` | WhatsApp app secret (alternative). |
| `WEBHOOK_VERIFY_TOKEN` | Optional generic webhook verification token. |
| `WEBHOOK_SIGNING_SECRET` | HMAC signing secret for generic webhooks. |
| `EMAIL_FROM_NAME` | Display name for transactional email (default: `Talk2Pay`). |
| `SENTRY_DSN` | Optional Sentry DSN. |
| `UPTIMEROBOT_API_KEY` | Optional uptime-monitoring credential. |
| `ADMIN_SECRET_PATH` | Optional admin secret path setting. |

### CI and production E2E secrets

The production E2E workflow requires these GitHub Actions secrets:

- `E2E_DEMO_BUSINESS_ID`
- `E2E_DEMO_WIDGET_API_KEY`
- `E2E_LEAD_PAGE_URL`
- `E2E_OWNER_TOKEN`

## Testing

### Python tests

```bash
pip install pytest
PYTHONPATH=. pytest -q
PYTHONPATH=. pytest -q tests/test_integration.py
```

### Static checks

```bash
python -m compileall -q backend main.py
python scripts/ui_quality_gate.py
python scripts/check_html_links.py
```

### Production E2E

```bash
npm install
npx playwright install --with-deps chromium webkit
E2E_BASE_URL=https://conversapay.org \
E2E_DEMO_BUSINESS_ID=... \
E2E_DEMO_WIDGET_API_KEY=... \
E2E_LEAD_PAGE_URL=... \
E2E_OWNER_TOKEN=... \
npx playwright test
```

Browser matrix: desktop Chrome, Safari WebKit, and Chrome mobile.

## CI/CD

GitHub Actions workflows:

- `backend-tests.yml`: Python deps, compile, UI/link quality gates, delivery contracts, full pytest suite.
- `production-e2e.yml`: manually triggered Playwright matrix.
- `production-smoke.yml`: production smoke checks.
- `php-lint.yml`: PHP linting for the WordPress plugin.
- `check-html-links.yml`: HTML link validation.
- `public-brand-contract.yml`: public branding contract checks.

Deployment is configured via `render.yaml` targeting Render.com. Health check path: `/ready`.

## Database and migrations

The baseline database definition is `database/full_schema_bootstrap.sql`. It is idempotent and creates the core schema, indexes, RLS policies, grants, and database functions.

Incremental migrations are stored in `database/migrations/` and are applied in filename order. The migration runner records each migration name and SHA-256 checksum in `public.schema_migrations`.

Important database functions:

- `user_owns_business`: tenant ownership helper used by RLS policies.
- `mark_email_verified`: controlled email-verification state transition.
- `claim_webhook_event`: webhook idempotency/replay claim.
- `update_order_payment_atomic`: atomic order/payment update for payment events.
- `consume_site_lead_rate_limit`: transactional site-builder lead rate limiting.

## Repository layout

```text
backend/
  middleware/       Authentication, tenant guards, rate limits, request context
  models/           Pydantic schemas
  routers/          FastAPI route handlers (auth, businesses, products, chat,
                    orders, payments, analytics, dashboard, site_builder,
                    stripe_webhook, whatsapp, reconciliation, api_keys,
                    admin, onboarding, subscription, widget, dev_simulator)
  scripts/          Migration and admin utility scripts
  services/         Stripe, PayMe, Cardcom, sessions, migrations, monitoring,
                    reconciliation, billing, money, product search,
                    widget auth, WhatsApp, email, AI (Gemini)
  static/           Backend-delivered static assets (robots.txt, sitemap.xml)
  config.py         Centralized settings via pydantic-settings
  dependencies.py   Request-scoped Supabase client providers
database/
  full_schema_bootstrap.sql
  migrations/
docs/               API, onboarding, production E2E, infrastructure phase notes
frontend/
  css/              Global styles
  html/             All application HTML pages
  images/
  js/               Dashboard, widget, onboarding, email-guard scripts
scripts/            HTML link checker and UI quality gate
Site Builder/       Standalone site-builder sub-application
tests/              Python integration and contract tests
tests/e2e/          Playwright production E2E tests
wordpress-plugin/   WordPress chat widget plugin (PHP)
main.py             FastAPI application entrypoint (v2.5.0)
render.yaml         Render.com deployment configuration
requirements.txt    Python dependencies
package.json        Playwright tooling
```

## Current implementation notes

- The main branch retains the synchronous Supabase client architecture for compatibility with existing authentication and middleware behavior.
- Request-scoped dependency providers exist in `backend/dependencies.py`, but not every router has been migrated to consume them yet.
- The active payment provider is runtime-configurable via `PAYMENT_PROVIDER`. Cardcom is integrated at the service level; its webhook router is a deprecated stub.
- The background migration task keeps liveness fast; `/ready` is the appropriate signal for database-backed readiness.
- `billing_reconciliation.py` provides pure billing-state helpers (effective plan, retry logic) used by reconciliation jobs and webhook handlers.
