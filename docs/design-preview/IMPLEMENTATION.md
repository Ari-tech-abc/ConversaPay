# Approved design implementation

The Forest / Mint / Warm White direction has been applied to the application's HTML sources. Product copy and API operations are preserved; copy review and production deployment are separate next steps.

## Shared implementation

- `frontend/css/talk2pay-theme.css` supplies Rubik typography, semantic tokens, responsive layouts, component styling and reduced-motion support. The delivery router places it after page-local and legacy styles.
- `frontend/js/workspace-ui.js` supplies workspace navigation, an accessible mobile drawer, inline field validation and the repeating marketing conversation demonstration.
- Every HTML page under `frontend/html`, both root policy copies, and the legacy Site Builder source load the theme. The dormant Site Builder is styled without introducing a new application route.
- Dashboard and account/integration pages expose real links to catalog, orders, import, profile, settings, plans, the widget guide, WordPress, AI setup and API/integrations. Existing forms, authentication, exports, catalog actions and billing operations remain connected to their existing scripts and APIs.
- The home conversation stays readable for approximately 13.5 seconds, fades its content for 750ms and restarts progressively. It pauses outside the viewport, in a hidden tab, under reduced-motion preferences, or when stopped by the user. It is illustrative and never charges a customer.
- Browser validation balloons are replaced by inline messages associated with fields using `aria-describedby` and `aria-invalid`. Constraint validation still prevents invalid submissions; valid corrected fields clear their messages.

## Local review

`node docs/design-preview/review-server.cjs` opens the actual delivery pages at `http://127.0.0.1:4319`. It renders HTML with the offline test environment, serves fixture GET responses, labels the preview as illustrative, and rejects all mutation requests. It does not connect to production data. The original concept remains at port 4318.

## Verification

- `tests/test_design_system.cjs`: 86 checks over all 22 delivery HTML pages at 1440px, 768px and 375px; navigation, mobile drawer, inline validation, automatic conversation reset and reduced motion.
- `tests/test_ux_regressions.cjs`: 24 existing UX regressions, including English copy, partial saves, API errors, modal keyboard behavior and mobile layouts.
- `tests/test_frontend_security.cjs`: existing import/API key escaping and password recovery regressions.
- `python -m unittest tests.test_application_security`: 12 composed-application checks, all passing.

Screenshots are generated into the ignored `live-review` directory by the design test. Set `TEST_PYTHON`, `PLAYWRIGHT_MODULE` and `PLAYWRIGHT_CHANNEL` when running on a host without the default runtimes. No deployment has been performed.
