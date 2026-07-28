# Talk2Pay, Apple-readiness report

## Current state

Talk2Pay is the official product and project name. The existing `conversapay.org` domain and technical `conversapay` identifiers remain active only for infrastructure and backward compatibility.

The polish and security hardening work is merged into `main`. This report remains evidence-based: repository and CI evidence are not the same as staging, browser, database, or production evidence.

## Implemented on `main`

- Talk2Pay is the canonical public brand at the delivery boundary, including titles, visible navigation, widget UI, email copy, API documentation, and Site Builder API naming.
- Shared product polish layer for authenticated, admin, billing, setup, legal, result, builder, and inbox surfaces.
- Hebrew RTL widget demo with responsive and keyboard-focusable controls.
- Real Site Builder lead persistence, owner-scoped inbox, status lifecycle, and RLS policies.
- Separate visible company field and hidden honeypot field. A real company value is no longer treated as spam.
- Atomic Postgres rate limiting for public lead intake, keyed by business and hashed client IP.
- Mandatory Origin validation against configured application origins and the business's registered custom domains.
- Idempotent lead migration policies and repeatable rate-limit function installation.
- Protected inbox route exposed through `/leads` and dashboard navigation.
- Local link validation and Talk2Pay product contract checks wired into CI.

## Compatibility boundary

The following `conversapay` forms are intentionally retained and are not public branding: the current domain, legacy storage keys, database/API identifiers, DOM root IDs, asset filenames, and deployment paths. Renaming them without a migration would break existing clients.

## Honest scorecard

| Area | Score now | Limitation |
|---|---:|---|
| Product concept and differentiation | 7.5/10 | Needs real customer proof and competitive evidence. |
| Product clarity | 6.8/10 | Messaging still needs customer-tested positioning. |
| Branding and naming consistency | 9.1/10 | Source and delivery boundary now use Talk2Pay; compatibility strings remain documented. |
| Hebrew and RTL quality | 8.8/10 | Browser and copy review across every state still required. |
| Shared visual language | 8.7/10 | Legacy CSS layers remain and need consolidation, not just overrides. |
| Site Builder behavior | 8.9/10 | Requires applied migration and real submission smoke test. |
| Lead security | 8.7/10 | Requires staging abuse test and multi-instance verification. |
| Tenant isolation | 8.8/10 | Requires database-applied RLS negative tests. |
| Accessibility | 8.2/10 | Requires browser audit with keyboard and screen reader checks. |
| Responsive quality | 8.2/10 | Requires visual regression at 320, 375, 768, 1024, and 1440px. |
| Maintainability | 8.2/10 | Delivery-boundary rewrites and legacy CSS are still technical debt. |
| CI and automated checks | 8.8/10 | Fresh post-merge run must be recorded for the latest main commits. |
| Production readiness | 7.0/10 | Requires fresh production smoke evidence for the latest deploy. |
| Apple presentation readiness | 7.0/10 | Do not present as certified until environment-dependent gates pass. |

## Release gates

1. Observe a fresh green CI run for the latest `main` hardening and rebrand commits.
2. Apply the lead migration in staging and verify create, reject honeypot, accept company, rate-limit, origin, list, update, and cross-business denial cases.
3. Run browser smoke and visual checks at 320, 375, 768, 1024, and 1440px across public, auth, dashboard, builder, inbox, billing, admin, legal, payment, and widget routes.
4. Verify the live host matches `main`, including Talk2Pay brand, pricing, copy, release header, and payment routes.
5. Run a legal review of privacy, terms, refunds, and payment wording.
6. Only then recalculate the Apple-facing score.

## Rule

No responsible reviewer should claim a general 9/10 from source inspection alone. The code-level branding and lead-security blockers are addressed on `main`; the remaining work is environment verification and measured product proof.
