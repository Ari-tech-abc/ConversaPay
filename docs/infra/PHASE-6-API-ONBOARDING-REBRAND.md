# Phase 6: API Documentation, Onboarding, and Rebrand

Status: Draft

## Scope

- Publish a customer-facing OpenAPI reference for API-key users.
- Document authentication, business scope, rate limits, errors, webhooks, and sandbox/live behavior.
- Complete a self-service onboarding checklist for catalog setup, payment connection, widget installation, and WhatsApp.
- Add an explicit sandbox/test mode and a safe path to live payments.
- Audit public-facing copy, metadata, assets, storage keys, and API identifiers for the Talk2Pay rebrand without breaking compatibility.
- Remove tracked runtime artifacts such as `__pycache__` and document the migration rules.

## Acceptance criteria

- A new business can reach a test conversation and payment in a guided flow.
- API customers can discover limits, payloads, signatures, and examples without private access.
- Sandbox actions cannot create live charges.
- Legacy ConversaPay identifiers remain only where compatibility requires them and are documented.
