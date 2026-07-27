# Talk2Pay API

The API is served under `/api/v1`. Authentication uses a bearer token for dashboard operations and a business-scoped API key for customer integrations.

## Production rules

- Never send secret keys from browser code.
- Every API key belongs to exactly one business.
- Payment and webhook events must be idempotent.
- Use `X-Correlation-ID` when tracing a request.
- Respect the rate-limit headers returned by the API.

## Core domains

- `/auth`: registration, login, OAuth, and verification.
- `/businesses`: business setup and ownership.
- `/products`: catalog management.
- `/chat`: AI conversations and checkout recommendations.
- `/orders`: order creation and lookup.
- `/payments`: checkout creation and verification.
- `/subscription`: plan state and cancellation.
- `/widget`: installation and widget access.
- `/webhooks`: signed integration callbacks.

OpenAPI is available in development at `/docs` and `/redoc`. In production, publish an authenticated or separately exported reference rather than exposing operational internals publicly.
