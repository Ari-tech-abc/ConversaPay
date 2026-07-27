# Talk2Pay Customer API

The FastAPI service exposes an OpenAPI schema in development at `/docs` and `/openapi.json`. Production deployments should publish a reviewed, authenticated reference from the same schema.

## Core areas

- `/api/v1/auth/*`: account creation and authentication
- `/api/v1/businesses/*`: business scope
- `/api/v1/products/*`: catalog management
- `/api/v1/orders/*`: order creation and lookup
- `/api/v1/payments/*`: checkout and payment verification
- `/api/v1/webhooks/*`: signed integration callbacks
- `/api/v1/widget/*`: website widget configuration

API keys must be scoped to one business. Never expose service-role credentials in a browser, plugin, or generated site. Treat webhook secrets as write-only credentials and rotate them after suspected exposure.

## Environments

Use sandbox/test credentials and test payment methods before enabling live provider keys. A live payment must never be created from a sandbox request, and every provider callback must be signature-verified and idempotent.
