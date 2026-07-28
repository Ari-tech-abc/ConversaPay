# ConversaPay, Apple-readiness pass

## Scope

This branch is the controlled product-improvement pass for presenting ConversaPay as a serious startup product to a large technology company. The work prioritizes one canonical brand, a coherent visual language, Hebrew-first RTL copy, real product behavior, tenant isolation, and repeatable quality gates.

## Implemented changes

- Added `frontend/html/apple-ready-polish.css` as the final shared visual layer for non-landing product surfaces.
- Added delivery-boundary branding and Hebrew-first copy normalization in `main.py`, with an `X-ConversaPay-Release` marker for staging verification.
- Canonicalized duplicate payment-success and payment-canceled entry files into route aliases without dropping query strings or fragments.
- Made the widget demo Hebrew-first, RTL, responsive, keyboard-focusable, and presentation-ready.
- Added `lead_submissions` migration with business ownership indexes, status lifecycle, timestamps, and RLS policies.
- Connected generated Site Builder forms to a real backend endpoint with validation, honeypot handling, stored source/page metadata, and tenant-scoped owner inbox APIs.
- Added `frontend/html/leads.html` as a protected inbox surface for reviewing and updating lead status.
- Added contract tests for brand delivery, RTL, generated forms, lead persistence, owner inbox behavior, and the visual demo surface.
- Added delivery-aware HTML quality and local-link gates, including canonical payment routes.

## Verification matrix

| Area | Current assessment | Evidence |
|---|---:|---|
| Canonical brand | 9.2/10 pending staging | Server transform and release header are implemented; live host still needs verification. |
| RTL and Hebrew copy | 9.1/10 pending browser pass | Routed UI labels are normalized and widget demo is Hebrew-first. |
| Shared visual language | 9.0/10 pending visual regression | Final product layer is injected across routed product surfaces. |
| Site Builder behavior | 9.1/10 pending migration smoke test | Generated forms now persist leads and owners can update status. |
| Accessibility foundations | 9.0/10 pending browser audit | Labels, live regions, focus states, reduced motion, and touch targets are covered in source. |
| Tenant isolation | 9.0/10 pending database apply | Owner queries are business-scoped and the lead table has RLS policies. |
| Maintainability | 8.9/10 | Delivery contract and focused tests are in place; legacy CSS consolidation remains technical debt. |
| Production readiness | 8.5/10 | Branch is implementation-ready, not production-certified until staging and live checks pass. |

## Verification gates still running or environment-dependent

1. CI must finish green after the latest lead and link-check commits.
2. Apply `20260728_site_builder_leads.sql` in staging, then exercise create, list, update, and unauthorized-access cases.
3. Run browser smoke tests at 320, 375, 768, 1024, and 1440px for public, auth, dashboard, builder, inbox, billing, admin, and legal routes.
4. Verify payment success, cancellation, OAuth callback, widget loading, and admin authorization in a non-production environment.
5. Deploy the branch to staging and confirm the release header, canonical brand, pricing, and page content match the branch rather than the stale public deployment.
6. Run a legal review of privacy, terms, refunds, and payment wording before making external claims.

## Release rule

Do not present this as a completed Apple-ready release until the CI checks are green, the migration is applied in staging, the browser matrix passes, and the live host matches this branch. No automatic merge was performed.
