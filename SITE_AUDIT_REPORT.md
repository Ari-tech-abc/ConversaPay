# ConversaPay audit and repair report

Branch: `fix/critical-payment-widget-security`

## Tier model

The app now uses only `plan_type`: `free`, `pro`, `premium`. The obsolete boolean concept `is_pro` was removed from the edited widget, WhatsApp, and chat paths.

## Changes in this pass

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

## Known integration step

Add `<script src="/frontend/js/premium-builder-link.js" defer></script>` to `frontend/html/dashboard.html` after the existing dashboard script. The builder is expected at `/site-builder.html` in production, or served separately at the builder origin during development.

## Important remaining backend work

Before production, harden the generic webhook ownership and signature paths, protect the development payment simulator with authentication, make PayMe idempotency atomic, and update Israeli legal text with a qualified Israeli attorney. These are backend/legal controls, not cosmetic edits.
