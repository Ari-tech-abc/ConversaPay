# Talk2Pay — Project Summary

Every file in the repository with a one-to-two line description.

---

## Root

| File | Summary |
| --- | --- |
| `main.py` | FastAPI composition root (v2.5.0). Registers all middleware, routers, health/readiness endpoints, and launches background migrations on startup. |
| `render.yaml` | Render.com deployment configuration: web service, build/start commands, health-check path, and all environment variable declarations. |
| `requirements.txt` | Python dependency list covering FastAPI, Supabase, Stripe, PayMe/Cardcom HTTP clients, Gemini AI, Resend email, Redis, asyncpg, Playwright tooling, and more. |
| `Dockerfile.txt` | Docker build instructions for containerised deployment. |
| `gitignore.txt` | Git ignore rules for the repository. |
| `README.md` | Full project documentation: architecture, security model, payment lifecycle, environment variables, testing, CI/CD, and repository layout. |

---

## backend/

| File | Summary |
| --- | --- |
| `backend/__init__.py` | Package marker for the backend module. |
| `backend/config.py` | Centralised settings via `pydantic-settings`. Defines all environment variables, path helpers, and a production-safety guard (`DEBUG` must be false in production). |
| `backend/dependencies.py` | FastAPI dependency providers that yield request-scoped Supabase anon and service-role clients. |

### backend/middleware/

| File | Summary |
| --- | --- |
| `auth.py` | Supabase Auth bearer-token validation middleware; exposes `require_auth` and `AuthUser` for protected routes. |
| `auth_rate_limit.py` | Per-IP rate limiting applied specifically to authentication endpoints to slow brute-force attempts. |
| `correlation.py` | Injects a `X-Correlation-ID` header into every request/response for distributed tracing. |
| `rate_limiter.py` | In-memory sliding-window `RateLimiter` class and `get_client_ip` helper used across the application. |
| `rate_limiter_profiles.py` | Pre-configured rate-limiter instances (profiles) for different endpoint categories. |
| `request_context.py` | Stores per-request context (correlation ID, user) in a `contextvars.ContextVar` for use in services. |
| `tenant_guard.py` | Business ownership guard; raises 403 if the authenticated user does not own the requested business. |

### backend/models/

| File | Summary |
| --- | --- |
| `schemas.py` | All Pydantic request and response models. Monetary fields use `Decimal`; includes order, payment, product, business, auth, and webhook schemas. |

### backend/routers/

| File | Summary |
| --- | --- |
| `__init__.py` | Exports all router modules for clean import in `main.py`. |
| `admin.py` | Admin-only endpoints for user and platform management, protected by admin secret path. |
| `admin_password.py` | Admin password-change endpoint with additional secret-path guard. |
| `analytics.py` | Business analytics endpoints: revenue, order counts, and conversion metrics for authenticated owners. |
| `api_keys.py` | CRUD for per-business widget API keys; keys are stored as HMAC-SHA256 hashes. |
| `auth.py` | Authentication routes: sign-up, login, logout, OAuth callback, password reset, and profile bootstrap. |
| `businesses.py` | CRUD for tenant businesses; enforces ownership on all mutating operations. |
| `cardcom_webhook.py` | Deprecated stub router for Cardcom webhooks (Stripe is now the primary webhook provider). |
| `chat.py` | Public chat endpoint; rate-limited per business, powered by Gemini AI, with widget-auth enforcement. |
| `dashboard.py` | Aggregated dashboard data endpoint for authenticated business owners. |
| `dev_simulator.py` | Non-production only: `POST /orders/{id}/mark-paid` for simulating payments; requires auth + business ownership. |
| `email_verification.py` | Email verification token validation endpoint; calls `mark_email_verified` RPC on success. |
| `frontend.py` | Serves all static frontend HTML files and assets from `frontend/`. |
| `logs.py` | Retrieves conversation and activity logs for authenticated business owners. |
| `onboarding.py` | First-login flow: ensures profile and starter business exist after Supabase Auth sign-in or OAuth. |
| `orders.py` | Public order creation (`POST /orders/pay`) and order status retrieval; prices sourced server-side. |
| `payments.py` | Authenticated payment endpoints: create Stripe Checkout session, confirm session (read-only), subscription checkout. |
| `products.py` | CRUD for business products; enforces ownership and validates monetary fields. |
| `profile.py` | Authenticated profile read/update endpoints for the current user. |
| `reconciliation.py` | `POST /reconciliation/orders`: re-checks stale pending payments against Stripe for authenticated owners. |
| `safe_auth.py` | Hardened auth wrappers that return generic error messages to prevent user enumeration. |
| `site_builder.py` | Site-builder endpoints: token validation, lead submission with transactional rate limiting. |
| `stripe_webhook.py` | Stripe webhook handler: signature verification, idempotency via `claim_webhook_event`, atomic order/payment update. |
| `subscription.py` | Subscription management: plan status, upgrade, and cancellation endpoints. |
| `webhooks.py` | Generic signed-webhook receiver with HMAC verification. |
| `whatsapp.py` | WhatsApp Cloud API webhook verification and inbound message handling. |
| `widget.py` | Public widget configuration endpoint; enforces plan and API-key checks via `widget_auth`. |

### backend/scripts/

| File | Summary |
| --- | --- |
| `apply_migration.sql` | Raw SQL helper script for manually applying a single migration. |
| `create_admin_user.py` | One-off script to create an admin user record in the database. |
| `migrate_email_verification.py` | One-off migration script for the email-verification schema change. |
| `run_migration.py` | CLI wrapper to invoke the migration runner outside of the application lifecycle. |

### backend/services/

| File | Summary |
| --- | --- |
| `billing_reconciliation.py` | Pure billing-state helpers: `effective_plan`, `should_retry_invoice`, and status normalisation used by reconciliation and webhook handlers. |
| `cardcom_service.py` | Cardcom v11 Low Profile integration: creates hosted payment pages and verifies transactions via the Cardcom API. |
| `email_service.py` | Transactional email sending via the Resend API (verification, password reset, notifications). |
| `gemini_service.py` | Gemini AI client wrapper for generating conversational chat responses. |
| `migration_runner.py` | Applies SQL migrations in filename order, records SHA-256 checksums in `schema_migrations`, and exposes migration status for health checks. |
| `money.py` | Exact monetary helpers (`money`, `multiply_money`, `money_db`) using `Decimal` and `ROUND_HALF_UP`. |
| `monitoring_service.py` | Application monitoring initialisation (Sentry, UptimeRobot integration). |
| `observability.py` | Error-tracking initialisation (Sentry DSN setup). |
| `payment_adapters.py` | Provider-agnostic checkout adapter layer: `StripeCheckoutAdapter`, `PayMeCheckoutAdapter`, and `get_checkout_adapter()` factory. |
| `product_service.py` | Product search and retrieval service with keyword/semantic scoring; formats products for AI consumption. |
| `reconciliation_service.py` | Queries stale pending payments and resolves them against Stripe via `update_order_payment_atomic`. |
| `session_service.py` | Session management helpers for Supabase Auth tokens. |
| `stripe_service.py` | Stripe API wrapper: checkout session creation, retrieval, subscription management, and minor-unit conversion. |
| `subscription_service.py` | Business subscription state helpers: plan lookup, upgrade/downgrade logic. |
| `webhook_security.py` | HMAC signature verification utilities for generic and provider-specific webhooks. |
| `whatsapp_security.py` | Encrypts/decrypts WhatsApp credentials at rest; wraps profile read/write to transparently handle sensitive fields. |
| `widget_auth.py` | Authorises public widget/chat requests: demo business bypass, plan check, and HMAC API-key validation. Never trusts Origin/Referer headers. |

### backend/static/

| File | Summary |
| --- | --- |
| `robots.txt` | Search-engine crawl directives. |
| `sitemap.xml` | XML sitemap for SEO. |

---

## database/

| File | Summary |
| --- | --- |
| `full_schema_bootstrap.sql` | Idempotent baseline schema: all tables, indexes, RLS policies, grants, and core database functions (`user_owns_business`, `mark_email_verified`, `claim_webhook_event`, `update_order_payment_atomic`, `consume_site_lead_rate_limit`). |

---

## docs/

| File | Summary |
| --- | --- |
| `API.md` | API endpoint reference and usage examples. |
| `ONBOARDING.md` | Step-by-step user onboarding guide. |
| `PRODUCTION_E2E.md` | Instructions for running and interpreting production Playwright E2E tests. |
| `REBRAND.md` | Notes on the Talk2Pay / ConversaPay rebranding. |
| `infra/PHASE-1-SECURITY.md` | Security hardening phase: auth, RLS, headers, secrets. |
| `infra/PHASE-2-MULTITENANCY.md` | Multi-tenancy phase: tenant isolation, ownership guards. |
| `infra/PHASE-3-BILLING.md` | Billing phase: Stripe integration, subscription lifecycle. |
| `infra/PHASE-4-OBSERVABILITY.md` | Observability phase: Sentry, correlation IDs, monitoring. |
| `infra/PHASE-5-TESTING-CI.md` | Testing and CI phase: pytest suite, GitHub Actions workflows. |
| `infra/PHASE-6-API-ONBOARDING-REBRAND.md` | API cleanup, onboarding flow, and rebranding phase. |

---

## frontend/

### frontend/css/

| File | Summary |
| --- | --- |
| `main.css` | Global application stylesheet. |

### frontend/html/

| File | Summary |
| --- | --- |
| `home.html` | Public landing/home page. |
| `login.html` | User login page. |
| `register.html` | User registration page. |
| `forgot-password.html` | Password reset request page. |
| `auth-callback.html` | OAuth callback handler page. |
| `dashboard.html` | Authenticated business owner dashboard. |
| `profile.html` | User profile settings page. |
| `settings.html` | Business settings page (WhatsApp, widget, API keys). |
| `products.html` | Product management page (implied by products router). |
| `pay.html` | Public payment/order page shown to customers. |
| `payment-success.html` | Informational payment success page. |
| `payment-canceled.html` | Informational payment canceled page. |
| `success.html` | Generic success confirmation page. |
| `canceled.html` | Generic cancellation confirmation page. |
| `upgrade.html` | Plan upgrade / subscription page. |
| `leads.html` | Site-builder lead submissions view. |
| `setup-guide.html` | Widget and integration setup guide. |
| `widget-demo.html` | Live demo of the embeddable chat widget. |
| `wordpress.html` | WordPress plugin installation and configuration guide. |
| `admin-login.html` | Admin login page. |
| `admin-dashboard.html` | Admin management dashboard. |
| `admin-change-password.html` | Admin password change page. |
| `privacy.html` | Privacy policy page. |
| `terms.html` | Terms of service page. |
| `404.html` | Custom 404 error page. |
| `conversapay-ui.css` | Component-level UI stylesheet used within HTML pages. |

### frontend/js/

| File | Summary |
| --- | --- |
| `widget.js` | Embeddable chat widget script loaded by third-party sites; handles UI, messaging, and API communication. |
| `dashboard.js` | Dashboard page logic: loads analytics, orders, and business data from the API. |
| `business-onboarding.js` | Guides new users through business setup steps after first login. |
| `email-verification-guard.js` | Redirects unverified users to the verification prompt before accessing protected pages. |
| `premium-builder-link.js` | Shows/hides the site-builder link based on the user's subscription plan. |

---

## scripts/

| File | Summary |
| --- | --- |
| `check_html_links.py` | Validates all internal `href` and `src` links in frontend HTML files; used as a CI quality gate. |
| `ui_quality_gate.py` | Checks frontend HTML for required UI elements and branding consistency; used as a CI quality gate. |

---

## Site Builder/

| File | Summary |
| --- | --- |
| `README.md` | Documentation for the standalone site-builder sub-application. |
| `backend/__init__.py` | Package marker for the site-builder backend module. |
| `backend/routers/__init__.py` | Package marker for the site-builder routers module. |
| `frontend/index.html` | Site-builder frontend single-page application. |

---

## wordpress-plugin/

| File | Summary |
| --- | --- |
| `conversapay-chat.php` | WordPress plugin main file: registers the chat widget shortcode and admin settings page. |
| `admin.css` | Styles for the WordPress plugin admin settings page. |
| `README.md` | Installation and configuration instructions for the WordPress plugin. |

---

## tests/

| File | Summary |
| --- | --- |
| `tests/` | Python integration and contract tests covering auth enforcement, readiness, security headers, tenant isolation, email verification, payment lifecycle, webhook idempotency, rate limiting, schema contracts, observability, and frontend delivery. |
| `tests/e2e/` | Playwright production E2E tests covering the full user journey on desktop Chrome, Safari WebKit, and Chrome mobile. |
