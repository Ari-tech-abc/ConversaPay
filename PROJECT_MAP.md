# Talk2Pay — Project Map (Architectural)

> **Important:** `conversapay` is used as a technical/internal identifier in code, storage keys, and legacy paths. The public product brand is **Talk2Pay**.

---

## 1) Directory tree

```text
.
├── .env
├── .gitignore
├── Dockerfile
├── Dockerfile.txt
├── gitignore.txt
├── main.py
├── PROJECT_SUMMARY.md
├── README.md
├── render.yaml
├── requirements.txt
├── SUPABASE_SETUP.md
├── unify_html.ps1
│
├── backend/
│   ├── __init__.py
│   ├── config.py
│   ├── dependencies.py
│   │
│   ├── middleware/
│   │   ├── auth.py
│   │   ├── auth_rate_limit.py
│   │   ├── correlation.py
│   │   ├── rate_limiter.py
│   │   ├── rate_limiter_profiles.py
│   │   ├── request_context.py
│   │   └── tenant_guard.py
│   │
│   ├── models/
│   │   └── schemas.py
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── admin_password.py
│   │   ├── analytics.py
│   │   ├── api_keys.py
│   │   ├── auth.py
│   │   ├── businesses.py
│   │   ├── cardcom_webhook.py
│   │   ├── chat.py
│   │   ├── dashboard.py
│   │   ├── dev_simulator.py
│   │   ├── email_verification.py
│   │   ├── frontend.py
│   │   ├── logs.py
│   │   ├── onboarding.py
│   │   ├── orders.py
│   │   ├── payments.py
│   │   ├── products.py
│   │   ├── profile.py
│   │   ├── reconciliation.py
│   │   ├── safe_auth.py
│   │   ├── site_builder.py
│   │   ├── stripe_webhook.py
│   │   ├── subscription.py
│   │   ├── webhooks.py
│   │   ├── whatsapp.py
│   │   └── widget.py
│   │
│   ├── services/
│   │   ├── billing_reconciliation.py
│   │   ├── cardcom_service.py
│   │   ├── email_service.py
│   │   ├── gemini_service.py
│   │   ├── migration_runner.py
│   │   ├── money.py
│   │   ├── monitoring_service.py
│   │   ├── observability.py
│   │   ├── payment_adapters.py
│   │   ├── product_service.py
│   │   ├── reconciliation_service.py
│   │   ├── session_service.py
│   │   ├── stripe_service.py
│   │   ├── subscription_service.py
│   │   ├── webhook_security.py
│   │   ├── whatsapp_security.py
│   │   └── widget_auth.py
│   │
│   └── static/
│       ├── robots.txt
│       └── sitemap.xml
│
├── database/
│   └── full_schema_bootstrap.sql
│
├── docs/
│   ├── API.md
│   ├── ONBOARDING.md
│   ├── PRODUCTION_E2E.md
│   ├── REBRAND.md
│   └── infra/
│       ├── PHASE-1-SECURITY.md
│       ├── PHASE-2-MULTITENANCY.md
│       ├── PHASE-3-BILLING.md
│       ├── PHASE-4-OBSERVABILITY.md
│       ├── PHASE-5-TESTING-CI.md
│       └── PHASE-6-API-ONBOARDING-REBRAND.md
│
├── frontend/
│   ├── html/
│   │   ├── 404.html
│   │   ├── admin-change-password.html
│   │   ├── admin-dashboard.html
│   │   ├── admin-login.html
│   │   ├── auth-callback.html
│   │   ├── canceled.html
│   │   ├── conversapay-ui.css
│   │   ├── dashboard.html
│   │   ├── forgot-password.html
│   │   ├── home.html
│   │   ├── leads.html
│   │   ├── login.html
│   │   ├── pay.html
│   │   ├── payment-canceled.html
│   │   ├── payment-success.html
│   │   ├── privacy.html
│   │   ├── profile.html
│   │   ├── register.html
│   │   ├── settings.html
│   │   ├── setup-guide.html
│   │   ├── success.html
│   │   ├── terms.html
│   │   ├── upgrade.html
│   │   ├── widget-demo.html
│   │   └── wordpress.html
│   │
│   └── js/
│       ├── business-onboarding.js
│       ├── dashboard.js
│       ├── email-verification-guard.js
│       ├── premium-builder-link.js
│       └── widget.js
│
├── scripts/
│   ├── check_html_links.py
│   └── ui_quality_gate.py
│
├── Site Builder/
│   ├── README.md
│   ├── backend/
│   │   ├── __init__.py
│   │   └── routers/
│   │       └── __init__.py
│   └── frontend/
│       └── index.html
│
└── wordpress-plugin/
    ├── admin.css
    ├── conversapay-chat.php
    └── README.md
```

---

## 2) Module inventory

### Root

| File | Role |
| --- | --- |
| `main.py` | **Entrypoint / composition root**. Starts FastAPI v2.5.0, registers middleware + routers, runs background migrations on startup, exposes `/health`, `/ready`, public config, and a custom dual CORS handler for public vs authenticated surfaces. |
| `.env` | Local secrets / environment defaults. Contains Supabase, Gemini, PayMe, Resend, and app settings. Not committed. |
| `requirements.txt` | Python dependency lock for backend services. |
| `render.yaml` | Render.com service definition. |
| `Dockerfile` / `Dockerfile.txt` | Multi-stage Docker build. (`Dockerfile.txt` is a plain-text duplicate of `Dockerfile`.) |
| `unify_html.ps1` | PowerShell utility that rewrites HTML files to use `conversapay-ui.css` and removes old inline styles / CSS links. |
| `gitignore.txt` | Plain-text duplicate of `.gitignore`. |
| `PROJECT_SUMMARY.md` | Legacy per-file one-line summary (superseded by this document). |

### Backend core

| File | Role |
| --- | --- |
| `backend/config.py` | Centralized settings via `pydantic-settings`. Defines all env vars, path helpers, production guard (`DEBUG` must be false), and `is_production` / `is_development` flags. |
| `backend/dependencies.py` | Request-scoped Supabase client providers. **Not yet consistently used**: many routers create their own module-level client instead. |
| `backend/__init__.py` | Package marker. Declares `__version__ = "2.0.0"` (conflicts with `main.py`'s `2.5.0`). |

### Middleware

| File | Role |
| --- | --- |
| `backend/middleware/auth.py` | Supabase Auth bearer validation (`get_current_user`, `require_auth`), `AuthUser`, role checking (`RoleChecker`), plan helpers (`active_plan`, `is_pro_user`), business ownership guard. |
| `backend/middleware/auth_rate_limit.py` | Per-endpoint distributed rate limits for auth/password-reset/admin-login using in-memory Redis-backed limiter. |
| `backend/middleware/correlation.py` | Injects `X-Correlation-ID` and logs `request_complete` events. |
| `backend/middleware/rate_limiter.py` | Sliding-window rate limiter with Redis + local fallback. Defines named limiters (`chat`, `free_chat_session`, `widget_config`). |
| `backend/middleware/rate_limiter_profiles.py` | Preconfigured limiter instances (auth, payment, webhook). |
| `backend/middleware/request_context.py` | `ContextVar`-based correlation ID helpers and a JSON log formatter. Also defines a second `CorrelationIdMiddleware` class; only the one from `correlation.py` is wired in `main.py`. |
| `backend/middleware/tenant_guard.py` | Ownership verification helpers for Supabase service-role queries (business/resource ownership). |

### Models

| File | Role |
| --- | --- |
| `backend/models/schemas.py` | All Pydantic DTOs: orders, payments, products, customers, conversations, chat, profile, logs, API keys, webhooks, analytics, etc. Monetary fields use `Decimal`. |

### Routers (controllers)

| File | Role |
| --- | --- |
| `backend/routers/admin.py` | Admin authentication, domain restrictions, abuse reports, audit logging, stats. Returns 404 for unauthenticated to avoid leaking routes. |
| `backend/routers/admin_password.py` | Authenticated admin password rotation with secret-path guard. |
| `backend/routers/analytics.py` | Business analytics: revenue, order counts, conversion, product breakdowns. |
| `backend/routers/api_keys.py` | CRUD for widget API keys. Keys stored as HMAC-SHA256 hashes, tier/plan-gated. |
| `backend/routers/auth.py` | Legacy auth routes: signup, login, logout, OAuth callback, password reset, profile bootstrap. Also exposes helper functions (`get_user_profile`, `update_profile_row`) monkey-patched via `main.py` for WhatsApp credential encryption. |
| `backend/routers/businesses.py` | Business CRUD, domain-settings authorization with plan-aware caps. |
| `backend/routers/cardcom_webhook.py` | **Deprecated stub** (no active webhook handler). Cardcom is used at service level only. |
| `backend/routers/chat.py` | Public chat endpoint powered by Gemini. Rate-limited per business, enforces plan/API key/widget auth, can create orders/checkouts inline. |
| `backend/routers/dashboard.py` | Aggregated dashboard data + plan feature matrix + subscription gating helpers. |
| `backend/routers/dev_simulator.py` | Dev-only `POST /orders/{id}/mark-paid`. Disabled in production. |
| `backend/routers/email_verification.py` | Signup + resend-verification endpoints that sit in front of legacy auth routes. |
| `backend/routers/frontend.py` | HTML/static asset delivery, copy normalization (`ConversaPay` -> `Talk2Pay`), hidden admin pages by secret path, site-builder SPA delivery, fallback 404. |
| `backend/routers/logs.py` | Authenticated log CRUD + stats, business-scoped. |
| `backend/routers/onboarding.py` | Auth-compatible `/auth/me` and `/auth/oauth/session` that add onboarding state flags without changing legacy handlers. |
| `backend/routers/orders.py` | Order creation (public + authenticated), product validation, guest public order access via HMAC token. |
| `backend/routers/payments.py` | Provider-neutral checkout creation + payment history + WordPress plugin download endpoint. |
| `backend/routers/products.py` | Product CRUD, public catalog read by business. |
| `backend/routers/profile.py` | Authenticated profile/password/2FA/sessions/notifications/billing/export/delete. |
| `backend/routers/reconciliation.py` | Triggers `reconcile_orders` for pending payments older than N minutes. |
| `backend/routers/safe_auth.py` | Allow-listed authenticated profile response (prevents over-exposure). |
| `backend/routers/site_builder.py` | Premium site-builder generate/save/leads/inbox APIs. Lead submission is public and origin-restricted. |
| `backend/routers/stripe_webhook.py` | Stripe webhook processor with idempotency (`claim_webhook_event`), subscription + order atomic updates. |
| `backend/routers/subscription.py` | Subscription status + cancellation with Stripe sync. |
| `backend/routers/webhooks.py` | Generic webhook CRUD + signed public callbacks (WhatsApp/Telegram/Custom) + verification endpoint. |
| `backend/routers/whatsapp.py` | WhatsApp Cloud API webhook for PREMIUM: signature verification, Gemini reply, customer/ conversation handling. |
| `backend/routers/widget.py` | Public widget config with API-key enforcement; no Origin/Host trust. |

### Services

| File | Role |
| --- | --- |
| `backend/services/billing_reconciliation.py` | Pure billing-state helpers (effective plan, retry eligibility). |
| `backend/services/cardcom_service.py` | Cardcom v11 Low Profile adapter (create payment page + verify transaction). Not wired as the active provider in routers. |
| `backend/services/email_service.py` | Resend-based verification + password-reset email templates. |
| `backend/services/gemini_service.py` | Gemini AI client + prompt builder + checkout action parsing. |
| `backend/services/migration_runner.py` | Applies SQL migrations under a Postgres advisory lock; tracks status (`pending`, `in_progress`, `completed`, `failed`, `skipped`). |
| `backend/services/money.py` | Decimal rounding helpers (`money`, `multiply_money`, `money_db`). |
| `backend/services/monitoring_service.py` | Centralized Sentry + logging helper methods (error capture, performance measurement). |
| `backend/services/observability.py` | Initializes Sentry with safe defaults. |
| `backend/services/payment_adapters.py` | Provider-neutral checkout adapter protocol (`StripeCheckoutAdapter`, `PayMeCheckoutAdapter`). |
| `backend/services/product_service.py` | Keyword-scored product search. **Not imported by any router** (dead code / unused service). |
| `backend/services/reconciliation_service.py` | Stripe-session based reconciliation for pending payments. |
| `backend/services/session_service.py` | Conversation/message/customer CRUD in Supabase. |
| `backend/services/stripe_service.py` | Stripe checkout + subscription helpers (create/retrieve). |
| `backend/services/subscription_service.py` | Authoritative subscription state transitions from Stripe events. |
| `backend/services/webhook_security.py` | HMAC signature verification + `require_signed_request` dependency. |
| `backend/services/whatsapp_security.py` | Versioned encrypt/decrypt/redact for WhatsApp credentials; monkey-patches auth profile access to auto-migrate legacy plaintext. |
| `backend/services/widget_auth.py` | Widget authorization: demo business allowlist, API key hash validation, authenticated owner bypass. Explicitly rejects Origin/Referer/Host trust. |

### Frontend

| File | Role |
| --- | --- |
| `frontend/html/*.html` | Static HTML pages served by `backend/routers/frontend.py`. Includes landing, auth, dashboard, billing, legal, admin, and integration pages. |
| `frontend/html/conversapay-ui.css` | Component-level stylesheet shared across pages. |
| `frontend/js/widget.js` | Embeddable third-party chat widget. Loads config, manages session, renders messages + checkout cards. |
| `frontend/js/dashboard.js` | Dashboard SPA logic (auth, business, products, orders, analytics, integrations). |
| `frontend/js/business-onboarding.js` | Onboarding dialog for new users without a business name. |
| `frontend/js/email-verification-guard.js` | Patches `fetch` + startup probe to block unverified users and trigger resend. |
| `frontend/js/premium-builder-link.js` | Injects site-builder link into dashboard nav for PREMIUM users. |

### Database

| File | Role |
| --- | --- |
| `database/full_schema_bootstrap.sql` | Idempotent baseline schema + RLS policies + helper functions. |

### Docs / Infra

| File | Role |
| --- | --- |
| `docs/API.md` | High-level API domain reference. |
| `docs/ONBOARDING.md` | Merchant onboarding checklist + sandbox rule. |
| `docs/PRODUCTION_E2E.md` | Playwright production E2E test plan. |
| `docs/REBRAND.md` | Talk2Pay / ConversaPay rebranding migration rules. |
| `docs/infra/PHASE-*.md` | Phase-by-phase infrastructure plans (security, multitenancy, billing, observability, testing, onboarding). |

### Scripts / CI helpers

| File | Role |
| --- | --- |
| `scripts/check_html_links.py` | Validates internal links + anchors in `frontend/html/*.html`. |
| `scripts/ui_quality_gate.py` | Enforces HTML lang/dir + delivery-boundary copy contracts. **Currently fails unless `main.py` contains `APPLE_POLISH_LINK` and `X-ConversaPay-Release` tokens (not present).** |

### Site Builder

| File | Role |
| --- | --- |
| `Site Builder/backend/__init__.py` | Empty package stub. |
| `Site Builder/backend/routers/__init__.py` | Empty package stub. |
| `Site Builder/frontend/index.html` | PREMIUM site-builder SPA served by `backend/routers/site_builder.py`. |
| `Site Builder/README.md` | Standalone builder documentation (mostly aspirational; actual logic lives in the main backend). |

### WordPress plugin

| File | Role |
| --- | --- |
| `wordpress-plugin/conversapay-chat.php` | WordPress plugin: settings page, widget injection, shortcode. |
| `wordpress-plugin/admin.css` | Admin styles for plugin settings. |
| `wordpress-plugin/README.md` | Plugin installation + configuration guide. |

---

## 3) Data / request flow

```text
Browser / Widget / WhatsApp / WordPress plugin / Site Builder
        |
        v
FastAPI main.py (v2.5.0)
   ├── DualCORSMiddleware (public vs authenticated)
   ├── CorrelationIdMiddleware
   ├── AuthRateLimitMiddleware
   └── Background migration task (async, advisory-locked)
        |
        v
Routers
   ├── frontend.py → static HTML/asset delivery
   ├── auth / onboarding / safe_auth / email_verification → Supabase Auth + profiles
   ├── businesses / products / orders / payments → service-role Supabase + payment adapters
   ├── chat / widget → rate-limit + authz + Gemini + checkout adapter
   ├── stripe_webhook / whatsapp / webhooks → signature verification + service layer
   └── admin / api_keys / logs / analytics / subscription / reconciliation
        |
        v
Services layer
   ├── Stripe / PayMe / Cardcom (external HTTP)
   ├── Gemini (external AI)
   ├── Resend (email)
   ├── Redis (rate limiting, optional)
   └── Supabase / Postgres (primary data store)
        |
        v
Response
   ├── JSON API
   ├── HTML page
   ├── Redirect to provider checkout
   └── Webhook acknowledgment
```

---

## 4) Architectural weak points / observations (no code changes)

1. **Inconsistent client architecture** — Most routers create their own module-level `create_client()` instead of using `backend/dependencies.py`. Migration to DI is incomplete.
2. **Unused service** — `backend/services/product_service.py` is not imported anywhere.
3. **Deprecated router** — `backend/routers/cardcom_webhook.py` is an empty stub; active Cardcom integration lives in `backend/services/cardcom_service.py` but is not invoked by any router.
4. **Duplicate/legacy artifacts** — `Dockerfile.txt` and `gitignore.txt` are plain-text copies of `Dockerfile` and `.gitignore`.
5. **Version drift** — `backend/__init__.py` declares `2.0.0`; `main.py` declares `2.5.0`.
6. **Site Builder stub package** — `Site Builder/backend/*` contains only empty `__init__.py` files; real logic is in `backend/routers/site_builder.py`.
7. **Frontend quality gate mismatch** — `scripts/ui_quality_gate.py` expects `APPLE_POLISH_LINK` and `X-ConversaPay-Release` tokens that are not present in current `main.py`.
8. **Sensitive data in `.env`** — The `.env` in the working tree contains live-looking Supabase, Resend, PayMe, and Gemini credentials. This is a security risk if committed.

---

## 5) Files scanned (audit trail)

Scanned individually (non-exhaustive categories below; exact paths listed in Section 1 tree and Section 2 inventory):

- Root config/deploy: `.env`, `.gitignore`, `Dockerfile`, `Dockerfile.txt`, `gitignore.txt`, `render.yaml`, `requirements.txt`, `unify_html.ps1`, `SUPABASE_SETUP.md`, `PROJECT_SUMMARY.md`, `README.md`, `main.py`
- Backend core: `backend/__init__.py`, `backend/config.py`, `backend/dependencies.py`
- Middleware: 7 files under `backend/middleware/`
- Models: `backend/models/schemas.py`
- Routers: 27 files under `backend/routers/`
- Services: 17 files under `backend/services/`
- Static: `backend/static/robots.txt`, `backend/static/sitemap.xml`
- Database: `database/full_schema_bootstrap.sql`
- Docs: 6 top-level + 6 `docs/infra/` files
- Frontend HTML: 24 files under `frontend/html/`
- Frontend JS: 5 files under `frontend/js/`
- Scripts: 2 files under `scripts/`
- Site Builder: 4 files
- WordPress plugin: 3 files

Total non-binary, non-`__pycache__` files reviewed: ~110.

---

## 6) Uncertainties / open questions

| # | File(s) | Uncertainty |
| --- | --- | --- |
| 1 | `backend/routers/payments.py` | References `backend/templates/conversapay-chat.php` but actual plugin lives under `wordpress-plugin/`. Likely broken unless copied/symlinked at deploy. |
| 2 | `backend/config.py` `site_builder_dir` | Points to `conversapay-site-builder/frontend`, but repo directory is `Site Builder/` (space). Suggests rename/external-dependency mismatch. |
| 3 | `payme_service.py` vs `payment_adapters.py` | No standalone `payme_service.py` exists; PayMe logic is inline inside `payment_adapters.py`. |
| 4 | `cardcom_service.py` usage | Exists but is not wired into any router/adapter in scanned code. |
| 5 | `tests/` directory | Referenced in docs and `PROJECT_SUMMARY.md` but absent from the current file tree. |
| 6 | `package.json` | Referenced in docs/PROJECT_SUMMARY.md but absent from the current file tree. |
| 7 | `database/migrations/` directory | Referenced in config and docs but absent from the current file tree. |
| 8 | `ui_quality_gate.py` tokens | `APPLE_POLISH_LINK` and `X-ConversaPay-Release` are required but absent from `main.py`. |
