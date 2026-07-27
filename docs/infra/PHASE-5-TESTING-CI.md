# Phase 5: Testing and CI

Status: Draft

## Scope

- Add a Python test suite for auth, payments, orders, ownership checks, and subscription state transitions.
- Add integration tests for Stripe, PayMe, WhatsApp, generic webhooks, and the payment simulator guard.
- Add regression tests for RLS and cross-tenant isolation.
- Add frontend smoke checks for routes, HTML links, and critical landing-page interactions.
- Expand GitHub Actions to run linting, compile checks, unit tests, integration tests, and security checks before deploy.

## Acceptance criteria

- Pull requests fail when critical backend tests or compile checks fail.
- Webhook replay, invalid signatures, ownership failures, and payment edge cases are covered.
- Test credentials and production secrets never enter CI logs.
- The deployment workflow has a clear required-check gate.
