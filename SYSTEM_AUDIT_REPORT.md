# ConversaPay system audit

Date: 2026-07-25
Branch: `main`

## Fixed in this pass

- Added `/wordpress` and `/wordpress.html` routes for the WordPress operations page.
- Added a visible WordPress entry to the Dashboard navigation at response time, so existing cached HTML is no longer required to expose the screen.
- Added `X-Widget-Key` to the CORS preflight allow-list.
- Removed `localhost` from the default CORS allow-list. Local origins now require explicit environment configuration.
- Disabled interactive FastAPI `/docs` and `/redoc` in production.
- Verified Python syntax for the changed application routing code.

## Findings checked

- Dashboard-to-WordPress navigation: fixed.
- WordPress page route availability: fixed.
- Widget input rendering: widget messages use `textContent`, and the dashboard uses an escaping helper for server values inserted into HTML.
- WordPress admin output: escaped settings and page values were retained; settings use WordPress capability checks and the Settings API.
- CORS: production defaults are now restrictive; public widget endpoints still support cross-origin requests by design.
- Placeholder and localhost search: no matches were found in the repository search pass for the checked patterns.
- Open issues: none were returned by the repository issue search.

## Remaining verification note

GitHub Advanced Security is not enabled for this private repository, so native repository-wide secret scanning could not run. A targeted scan was attempted for the changed widget, WordPress, UI, and operations files. PHP linting was not available in the execution environment; the plugin should be linted in CI or a WordPress build environment before release.
