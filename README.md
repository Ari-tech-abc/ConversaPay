# ConversaPay

ConversaPay is a payment and conversational-commerce platform. It combines a FastAPI backend, a static frontend, Supabase/PostgreSQL persistence, Stripe Checkout and webhooks, WhatsApp Cloud API integration, an embeddable widget, and a WordPress plugin.

## Contents

- [Architecture](#architecture)
- [Threat model and security](#threat-model-and-security)
- [Orders and payment lifecycle](#orders-and-payment-lifecycle)
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
          FastAPI application (main.py)
                    |
       routers -> services -> Supabase/PostgreSQL
                    |                 |
              Stripe API        SQL migrations/RPCs
                    |
              Stripe webhooks
```

### Application layers

- `main.py` is the FastAPI composition root. It registers middleware, routers, health/readiness endpoints, and background migration startup.
- `backend/routers/` contains HTTP handlers for authentication, businesses, products, chat, orders, payments, analytics, dashboards, site builder, Stripe, and WhatsApp.
- `backend/services/` contains integrations and domain services, including Stripe, Gemini, email, sessions, monitoring, subscriptions, migrations, and WhatsApp secret handling.
- `backend/middleware/` contains authentication, tenant ownership, rate limiting, correlation IDs, and request context behavior.
- `backend/models/schemas.py` contains Pydantic request and response models. Monetary fields use `Decimal` in the current main branch.
- `database/full_schema_bootstrap.sql` contains the idempotent baseline schema. Incremental SQL changes live under `database/migrations/`.
- `frontend/` contains the static application and widget assets. `wordpress-plugin/` contains the WordPress integration.

The production API is mounted under `/api/v1`. FastAPI documentation is available locally when the environment is not production; production disables `/docs` and `/redoc`.

## Threat model and security

### Assets protected

- User identities, sessions, password-reset flows, and email-verification state.
- Tenant data: businesses, products, customers, conversations, orders, payments, logs, and API keys.
- Payment metadata and subscription state.
- WhatsApp access and verification credentials.
- Site-builder tokens and lead submissions.

### Trust boundaries

1. The browser, widget, WordPress plugin, WhatsApp, and Stripe are external callers.
2. FastAPI validates authentication, request shape, tenant ownership, rate limits, webhook signatures, and plan access.
3. Supabase/PostgreSQL is the persistence boundary and enforces RLS policies for authenticated access.
4. Service-role database access bypasses RLS, so server-side ownership checks remain mandatory.

### Controls implemented

- Supabase Auth bearer-token validation for protected routes.
- Tenant ownership checks through business ownership guards.
- PostgreSQL RLS policies for tenant-scoped tables.
- Stripe signature verification and webhook replay protection through `webhook_events`.
- HMAC verification for generic signed webhooks.
- Rate limiting for authentication, public order/chat flows, and site-builder lead submissions.
- Security headers including CSP, HSTS in production, `X-Content-Type-Options`, `X-Frame-Options`, Referrer Policy, and Permissions Policy.
- API keys are stored as hashes and widget access is checked against the business scope.
- WhatsApp access and verification tokens are encrypted at rest; verification lookup uses an HMAC digest. Decrypted access tokens are used only inside the WhatsApp send path and are not returned by API responses.
- Service errors returned to clients are intentionally generic in sensitive paths.

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
5. Monetary calculations use `Decimal` and are persisted as two-decimal values compatible with PostgreSQL `NUMERIC(12,2)`.
6. The order is stored as `pending` with `payment_status=pending`.

### Stripe Checkout

1. An authenticated owner calls `POST /api/v1/payments/checkout-session` for an order, or `POST /api/v1/payments/create-checkout-session` for a subscription.
2. The backend verifies business/order ownership.
3. Stripe receives minor units derived from an exact decimal amount, such as cents for two-decimal currencies.
4. The payment row stores the Stripe session metadata and remains pending until Stripe confirms the result.
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

For order payments, `backend/routers/stripe_webhook.py` calls the PostgreSQL RPC `update_order_payment_atomic`. The function updates the order and its latest payment inside one database transaction, locks the payment row, merges provider metadata, and sets `paid_at` for successful payments. If the order or payment update fails, the function raises and PostgreSQL rolls back the whole operation. This prevents a payment from being marked successful while its order remains pending.

Duplicate Stripe events are rejected or safely reprocessed through the webhook claim table. Failed processing is recorded as a failed webhook event so it can be retried according to the repository's webhook logic.

Subscription state is webhook-owned. `confirm-session` is read-only and does not mutate subscription state.

## Onboarding

1. A user signs up through the authentication routes.
2. Supabase Auth creates the identity.
3. ConversaPay creates a profile with free-plan defaults and an email-verification token.
4. The verification email is sent through the configured email provider.
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
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with development credentials, then start the API:

```bash
uvicorn main:app --reload
```

Useful local endpoints:

- `GET /health`: fast liveness response.
- `GET /ready`: database and optional Redis readiness checks.
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
| `ENVIRONMENT` | Runtime environment, for example `development`, `test`, or `production`. |
| `DEBUG` | Debug flag; must be false in production. |
| `API_PREFIX` | API route prefix, default `/api/v1`. |
| `CORS_ORIGINS` | Comma-separated allowed origins. |

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
| `WEBHOOK_VERIFY_TOKEN` | Optional generic webhook verification setting. |
| `WEBHOOK_SIGNING_SECRET` | HMAC signing secret for generic webhooks. |
| `EMAIL_FROM_NAME` | Display name for transactional email. |
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

Install pytest if it is not already installed:

```bash
pip install pytest
```

Run the full Python suite:

```bash
PYTHONPATH=. pytest -q
```

Run the main integration suite:

```bash
PYTHONPATH=. pytest -q tests/test_integration.py
```

The repository includes tests for authentication enforcement, readiness, security headers, tenant isolation, email verification, payment lifecycle contracts, webhook replay/idempotency, rate limiting, schema/bootstrap contracts, observability, and frontend delivery contracts.

### Static checks

```bash
python -m compileall -q backend main.py
python scripts/ui_quality_gate.py
python scripts/check_html_links.py
```

### Production E2E

Production E2E is a manually triggered Playwright workflow. Locally:

```bash
npm install
npx playwright install --with-deps chromium webkit
E2E_BASE_URL=https://conversapay-proj.onrender.com \\
E2E_DEMO_BUSINESS_ID=... \\
E2E_DEMO_WIDGET_API_KEY=... \\
E2E_LEAD_PAGE_URL=... \\
E2E_OWNER_TOKEN=... \\
npx playwright test
```

The browser matrix covers desktop Chrome, Safari WebKit, and Chrome mobile. Do not run production E2E against real customer data without an approved test account and cleanup plan.

## CI/CD

GitHub Actions workflows currently cover:

- `backend-tests.yml`: installs Python dependencies, compiles the backend, runs UI/link quality gates, delivery contracts, and the full pytest suite on pushes and pull requests to `main`.
- `production-e2e.yml`: manually triggered production Playwright matrix for desktop Chrome, Safari WebKit, and Chrome mobile.
- `production-smoke.yml`: production smoke checks.
- `php-lint.yml`: PHP linting for the WordPress plugin.
- `check-html-links.yml`: HTML link validation.
- `public-brand-contract.yml`: public branding contract checks.

Recommended merge gate: require backend tests, PHP lint, HTML/link checks, and the relevant production smoke/E2E evidence before deploying.

## Database and migrations

The baseline database definition is `database/full_schema_bootstrap.sql`. It is idempotent and creates the core schema, indexes, RLS policies, grants, and database functions.

Incremental migrations are stored in `database/migrations/` and are applied in filename order after the baseline bootstrap. The migration runner records each migration name and SHA-256 checksum in `public.schema_migrations`; changing an already-applied migration produces a checksum mismatch instead of silently rewriting history.

Important database functions include:

- `user_owns_business`: tenant ownership helper used by RLS policies.
- `mark_email_verified`: controlled email-verification state transition.
- `claim_webhook_event`: webhook idempotency/replay claim.
- `update_order_payment_atomic`: atomic order/payment update for Stripe order events.
- `consume_site_lead_rate_limit`: transactional site-builder lead rate limiting.

## Repository layout

```text
backend/
  middleware/       Authentication, tenant guards, rate limits, request context
  models/           Pydantic schemas
  routers/          FastAPI route handlers
  services/         Stripe, sessions, migrations, monitoring, WhatsApp, email, AI
  static/           Backend-delivered static assets
database/
  full_schema_bootstrap.sql
  migrations/
docs/               API, onboarding, production E2E, infrastructure notes
frontend/           Static frontend, HTML, JavaScript, images
tests/              Python integration and contract tests
tests/e2e/          Playwright production E2E tests
wordpress-plugin/  WordPress chat widget plugin
main.py             FastAPI application entrypoint
requirements.txt    Python dependencies
package.json        Playwright tooling
```

## Current implementation notes

- The main branch intentionally retains the synchronous Supabase client architecture for compatibility with existing authentication and middleware behavior.
- Request-scoped dependency providers exist in `backend/dependencies.py`, but not every existing router has been migrated to consume them yet. Treat this as an incremental cleanup area rather than assuming all global clients have already been removed.
- The background migration task keeps liveness fast, while `/ready` remains the appropriate signal for database-backed readiness.
