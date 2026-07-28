# ConversaPay, Apple-readiness report

## Current state

The Apple polish work is now merged into `main`, followed by a second hardening pass for the public Site Builder lead flow. This report is deliberately evidence-based: repository and CI evidence are not the same as staging, browser, database, or production evidence.

## Implemented on `main`

- Canonical ConversaPay branding and Hebrew-first delivery normalization.
- Shared product polish layer for authenticated, admin, billing, setup, legal, result, builder, and inbox surfaces.
- Hebrew RTL widget demo with responsive and keyboard-focusable controls.
- Real Site Builder lead persistence, owner-scoped inbox, status lifecycle, and RLS policies.
- Separate visible company field and hidden honeypot field. A real company value is no longer treated as spam.
- Atomic Postgres rate limiting for public lead intake, keyed by business and hashed client IP.
- Origin validation against configured application origins and the business's registered custom domains.
- Idempotent lead migration policies and repeatable rate-limit function installation.
- Protected inbox route exposed through `/leads` and dashboard navigation.
- Local link validation and product contract checks wired into CI.

## Evidence available

- Latest `main` commits include the security hardening, lead migration hardening, inbox navigation, and contract tests.
- The previous PR checks were green for Python tests, HTML local links, and PHP syntax.
- The current hardening commits are on `main`; a fresh post-merge CI result must still be observed for those commits.

## Honest scorecard

| Area | Score now | Limitation |
|---|---:|---|
| Product concept and differentiation | 7.5/10 | Needs real customer proof and competitive evidence. |
| Product clarity | 6.8/10 | Messaging still needs customer-tested positioning. |
| Branding and naming consistency | 8.9/10 | Live deployment verification still required. |
| Hebrew and RTL quality | 8.8/10 | Browser and copy review across every state still required. |
| Shared visual language | 8.7/10 | Legacy CSS layers remain and need consolidation, not just overrides. |
| Site Builder behavior | 8.9/10 | Requires applied migration and real submission smoke test. |
| Lead security | 8.7/10 | Requires staging abuse test and multi-instance verification. |
| Tenant isolation | 8.8/10 | Requires database-applied RLS negative tests. |
| Accessibility | 8.2/10 | Requires browser audit with keyboard and screen reader checks. |
| Responsive quality | 8.2/10 | Requires visual regression at 320, 375, 768, 1024, and 1440px. |
| Maintainability | 8.1/10 | Delivery-boundary rewrites and legacy CSS are still technical debt. |
| CI and automated checks | 8.8/10 | Fresh post-merge run must be recorded for the latest main commits. |
| Production readiness | 7.0/10 | Staging and live host are not verified from repository evidence alone. |
| Apple presentation readiness | 7.0/10 | Do not present as certified until environment-dependent gates pass. |

## Release gates

1. Observe a fresh green CI run for the latest `main` hardening commits.
2. Apply the lead migration in staging and verify create, reject honeypot, accept company, rate-limit, origin, list, update, and cross-business denial cases.
3. Run browser smoke and visual checks at 320, 375, 768, 1024, and 1440px across public, auth, dashboard, builder, inbox, billing, admin, legal, payment, and widget routes.
4. Verify the live host matches `main`, including brand, pricing, copy, release header, and payment routes.
5. Run a legal review of privacy, terms, refunds, and payment wording.
6. Only then recalculate the Apple-facing score.

## Rule

No responsible reviewer should claim a general 9/10 from source inspection alone. The code-level blockers are addressed on `main`; the remaining work is environment verification and measured product proof.
