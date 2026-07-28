# Talk2Pay production E2E

The production browser suite lives in `tests/e2e/production.spec.mjs` and runs against the Render service. It is intentionally manual because it creates one synthetic lead in the production inbox.

## Required CI secrets

- `E2E_DEMO_BUSINESS_ID`, an active demo business UUID.
- `E2E_DEMO_WIDGET_API_KEY`, a disposable active widget key.
- `E2E_LEAD_PAGE_URL`, a generated Talk2Pay page containing `#contactForm`.
- `E2E_OWNER_TOKEN`, a short-lived owner JWT for the demo business.

## Run locally

```bash
npm install
npx playwright install chromium webkit
E2E_DEMO_BUSINESS_ID=... \
E2E_DEMO_WIDGET_API_KEY=... \
E2E_LEAD_PAGE_URL=https://... \
E2E_OWNER_TOKEN=... \
npm run test:e2e:production
```

## Matrix

- Desktop Chrome.
- Safari engine through Playwright WebKit.
- Chrome Mobile emulation using Pixel 7.

## Pass criteria

- Home serves Talk2Pay and current prices.
- Widget opens, sends a message, receives an API response, and renders the assistant reply.
- Lead form accepts a real company value, confirms success, and the owner inbox contains exactly one matching lead.
- The test must not run with production credentials that can affect real customer data. Use a disposable demo business and a short-lived owner token.
