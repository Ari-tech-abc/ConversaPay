# Phase 1: Security Hardening

Status: Draft

## Scope

- Keep the development payment simulator unavailable in production and require authenticated business ownership in non-production.
- Verify signatures and ownership for every public webhook path, including provider-specific callbacks.
- Complete atomic PayMe webhook idempotency and duplicate-event handling.
- Apply endpoint-specific rate limits to authentication, payment, webhook, and chat surfaces.
- Add security-focused regression coverage before merge.

## Acceptance criteria

- No payment state can be changed by an unauthenticated or cross-business caller.
- Invalid, missing, replayed, or duplicate webhook events are rejected or safely ignored.
- Production startup does not register development-only payment routes.
- Sensitive endpoints return rate-limit headers and consistent 429 responses.
