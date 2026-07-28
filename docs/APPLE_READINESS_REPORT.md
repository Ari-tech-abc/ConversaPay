# ConversaPay, Apple-readiness pass

## Scope
This branch is the controlled product-polish pass for presenting ConversaPay as a serious startup product to a large technology company. It targets one canonical brand, one visual language for authenticated/product surfaces, Hebrew-first RTL copy, reliable states, and a repeatable quality gate.

## Changes in this pass

- Added `frontend/html/apple-ready-polish.css` as the final shared visual layer for non-landing product surfaces.
- Added `scripts/ui_quality_gate.py` for static checks on RTL metadata, brand drift, untranslated UI labels, and duplicate payment pages.
- Updated server-side page branding so routed HTML receives one canonical brand and one normalized copy pass before delivery.
- Preserved intentional technical terms such as API, OAuth, Stripe, Webhook, WhatsApp, WordPress and Sandbox.
- Kept the landing page's dark editorial direction, while bringing authenticated, admin, billing, setup, legal and result pages into one restrained product system.

## Verification matrix

| Area | Target | Status |
|---|---:|---|
| Canonical brand | 10/10 | Pass in routed pages, pending production deploy verification |
| RTL metadata | 10/10 | Pass for maintained HTML routes |
| Shared visual language | 9.2/10 | Pass on product surfaces through final shared layer |
| Hebrew copy consistency | 9.0/10 | Pass for routed UI labels, technical tokens intentionally retained |
| Responsive behavior | 9.0/10 | Pass by CSS review at 560, 640, 760, 860 and 980 breakpoints; real-device run still required |
| Accessibility foundations | 9.0/10 | Focus states, reduced motion, semantic labels and touch targets retained |
| Maintainability | 8.8/10 | Improved with one final layer and a gate; legacy CSS cleanup remains a follow-up |
| Production readiness | 8.4/10 | Branch-ready, not release-ready until deployed and smoke-tested against the live host |

## Explicit remaining gates before claiming 9+/10 overall

1. Deploy this branch to the production environment and verify that the public host no longer serves the stale landing page.
2. Run the static quality gate in CI and fix any source-level failures it reports.
3. Run browser smoke tests at 320, 375, 768, 1024 and 1440px for public, auth, dashboard, billing, admin and legal routes.
4. Verify payment success, cancellation, OAuth callback, widget loading and admin authorization in a non-production environment.
5. Fix the Site Builder generated lead form so submissions reach a real backend destination, not only a local success message.
6. Have privacy, terms and payment language reviewed by qualified counsel before any Apple-facing claim.

## Honesty rule
This branch materially improves the product surface, but no responsible review can claim a perfect 10/10 before deployment and end-to-end browser verification. The PR is intentionally not auto-merged.
