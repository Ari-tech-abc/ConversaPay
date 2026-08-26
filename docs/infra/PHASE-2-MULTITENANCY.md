# Phase 2: Multi-Tenancy and Row-Level Security

Status: Draft

## Scope

- Audit every business-owned table and every service-role query path.
- Enforce business ownership consistently for products, orders, payments, webhooks, API keys, analytics, and widget access.
- Add or complete Supabase Row Level Security policies for user and business data.
- Isolate API keys by business namespace and prevent cross-tenant lookup by identifier.
- Add negative tests proving tenant A cannot read or mutate tenant B data.

## Acceptance criteria

- Every tenant-owned record has a verified ownership path.
- RLS policies cover all production tables that contain tenant data.
- API-key authentication resolves to exactly one business scope.
- Cross-tenant access attempts fail closed with no data leakage.
