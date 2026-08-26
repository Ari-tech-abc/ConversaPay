# Talk2Pay Merchant Onboarding

## Guided checklist

1. Create and verify the account.
2. Create the business profile.
3. Add the first product with price, currency, description, and an active payment link.
4. Run a sandbox conversation and confirm the recommendation flow.
5. Connect the selected payment provider.
6. Install the widget on a staging domain.
7. Configure WhatsApp only after webhook verification succeeds.
8. Confirm an order appears in the dashboard.
9. Run the production readiness checklist.
10. Switch to live payment mode only after credentials, webhook signatures, and refund handling are verified.

## Sandbox rule

Sandbox and live credentials must be separate. The UI should make the current mode visible at every payment action and must never silently fall back from live to test or the reverse.
