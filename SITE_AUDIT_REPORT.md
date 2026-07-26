# ConversaPay audit and repair report

## Pass 3 — Frontend route audit and integration guide overhaul

Branch: `fix/frontend-route-audit-integration-guide`

Every `.html` file under `frontend/html/` was swept for dead `href`s, dead JS
redirects, relative-vs-root-absolute path errors, missing routes and missing DOM
IDs. No DOM IDs, event hooks or `fetch` paths were renamed.

### Broken routes found and fixed

| Where | Problem | Fix |
|---|---|---|
| `setup-guide.html`, `pay.html`, `terms.html`, `privacy.html` | `href="home.html"` resolved to `/home.html`, which had no route. Hard 404 on every logo and "back home" link. | Links point at `/`; `/home` and `/home.html` added as aliases in `main.py`. |
| `login.html` | `href="/forgot-password.html"` — no such route. Password reset was unreachable from the login screen. | Route added, link is now `/forgot-password`. |
| `register.html` | `/terms.html` and `/privacy.html` had no routes. Signup consent links 404'd. | Routes added, links are now `/terms` and `/privacy`. |
| `forgot-password.html` | `history.replaceState` rewrote the URL to `/forgot-password`, so a refresh mid-reset 404'd. | Route now exists. |
| `admin-change-password.html` | Stylesheet was loaded relatively (`conversapay-ui.css`), resolving to `/admin-<secret>/conversapay-ui.css`. Page rendered completely unstyled. | Absolute `/frontend/html/conversapay-ui.css`. |
| `admin-change-password.html`, `admin-dashboard.html` | `location.href = '/admin-login.html'` and `href="/admin-dashboard.html"` are deliberate 404s whenever `ADMIN_SECRET_PATH` is set. Logging out or arriving without a token dropped admins into an unrecoverable 404. | Both derive the route from the live `/admin-<secret>/` path segment, matching the logic already in `admin-login.html`. |
| `pay.html` | `login.html?next=` relied on a legacy `.html` route. | `/login?next=`. |
| `payment-success.html`, `payment-canceled.html` | `/dashboard.html`, `/upgrade.html` legacy paths. | `/dashboard`, `/upgrade`. |
| Global | The 404 handler returned raw JSON, so any mistyped URL showed a bare error object in the browser. | `_wants_html()` splits browser navigations from API calls: browsers get the new `404.html`, API clients keep the JSON body. |

### Pages added

- `frontend/html/404.html` — white card surface, purple primary action, light
  background tokens from `conversapay-ui.css`. Sends signed-out visitors to
  `/login` instead of `/dashboard`.

`forgot-password.html`, `terms.html` and `privacy.html` already existed as files;
only their routes were missing.

### JS execution blocks

Every `getElementById` call in every page was cross-checked against the markup —
no missing IDs remain. `setup-guide.html` bound its copy handler without a null
guard and threw if the block was ever removed; it is now guarded, as is the
reference row lookup in `payment-success.html`.

### Integration guide overhaul

`frontend/html/wordpress.html` (served at `/wordpress` and now also
`/integration-guide`) was rebuilt as a three-tab guide on the light design system:

1. **WordPress plugin** — packaging, upload, the settings-field map with the
   consequence of leaving each field blank, `[conversapay_chat]` shortcode,
   `do_shortcode()` usage, and a plugin-free `functions.php` snippet.
2. **Custom HTML** — the `<script>` embed, the full styled variant, the
   `data-*` attribute reference, `window.ConversaPayWidgetConfig`, the
   `ConversaPayWidget.open()/close()` API, and single-injection SPA loading.
3. **Troubleshooting and production checklist** — the silent UUID failure,
   401/403 responses from `backend/routers/widget.py`, which API paths are
   CORS-public, domain verification formatting rules, WhatsApp and Stripe
   webhooks, caching and CSP, plus a nine-item go-live checklist.

Every block is syntax highlighted, forced LTR inside the RTL page, and has a
copy button with an `execCommand` fallback for non-secure contexts. A
personalisation bar rewrites the domain, business ID and API key placeholders
across all snippets at once; values are kept in `localStorage` only.

### Still open (backend and legal, unchanged by this pass)

Harden generic webhook ownership and signature paths, authenticate the
development payment simulator, make PayMe idempotency atomic, and have the
Israeli legal text reviewed by a qualified Israeli attorney.

---

## Pass 2 — Tier model and site builder

Branch: `fix/critical-payment-widget-security`

### Tier model

The app now uses only `plan_type`: `free`, `pro`, `premium`. The obsolete boolean concept `is_pro` was removed from the edited widget, WhatsApp, and chat paths.

### Changes in this pass

| Path | Change |
|---|---|
| `backend/routers/dashboard.py` | Explicit tier entitlement matrix, corrected ILS pricing, corrected product inventory field, premium-only site builder entitlement, consistent dashboard responses. |
| `conversapay-site-builder/backend/routers/generator.py` | Added safer structured generation, strict input validation, HTML escaping, no raw AI error leakage, generated pages with semantic responsive markup. |
| `conversapay-site-builder/frontend/index.html` | Replaced the oversized builder UI with a cleaner responsive studio, working preview, vibe selection, error state, and HTML download. |
| `frontend/js/premium-builder-link.js` | Adds a verified PREMIUM-only sidebar link using `/api/v1/dashboard/features`. Load it after `dashboard.js`. |
| `frontend/html/home.html` | Earlier pass: corrected plan prices, CTA routing, domain metadata, and year. |
| `frontend/html/login.html` | Earlier pass: aligned login flow with backend and Supabase OAuth. |
| `frontend/html/register.html` | Earlier pass: aligned validation with the 8-character backend requirement. |
| `frontend/html/profile.html` | Earlier pass: uses `PUT /api/v1/auth/me`. |
| `frontend/html/forgot-password.html` | Earlier pass: supports Supabase recovery hash and password update. |
| `frontend/html/pay.html` | Earlier pass: public order summary and plan checkout flow. |
| `frontend/html/upgrade.html` | Earlier pass: uses ₪200 / ₪350 and the real checkout endpoint. |
| `backend/routers/chat.py` | Earlier pass: UUID order numbers, catalog prices, and tier checks via `plan_type`. |
| `backend/routers/widget.py` | Earlier pass: strict host matching and three-tier widget access. |
| `backend/routers/whatsapp.py` | Earlier pass: premium-only checks via `plan_type`, no `is_pro`. |

### Known integration step

Add `<script src="/frontend/js/premium-builder-link.js" defer></script>` to `frontend/html/dashboard.html` after the existing dashboard script. The builder is expected at `/site-builder.html` in production, or served separately at the builder origin during development.
