# Talk2Pay

Talk2Pay היא פלטפורמת SaaS לצ'אטבוט מכירות מבוסס AI. הלקוח מקבל ווידגט צ'אט שמוטמע באתר שלו, הבוט מכיר את המוצרים של העסק, יודע לתמחר ולהוציא לינק תשלום ישירות מתוך השיחה.

> שם הקוד הטכני: `conversapay`. שני השמות מתייחסים לאותו מוצר.

---

## תוכן עניינים

- [ארכיטקטורה](#ארכיטקטורה)
- [זרימת המשתמש](#זרימת-המשתמש)
- [תוכניות מנוי](#תוכניות-מנוי)
- [ספקי תשלום](#ספקי-תשלום)
- [מחסנית Middleware](#מחסנית-middleware)
- [אבטחה](#אבטחה)
- [פיתוח מקומי](#פיתוח-מקומי)
- [משתני סביבה](#משתני-סביבה)
- [בסיס נתונים](#בסיס-נתונים)
- [פריסה](#פריסה)
- [מבנה הריפו](#מבנה-הריפו)
- [בעיות ידועות](#בעיות-ידועות)

---

## ארכיטקטורה

```
Browser / Widget / WordPress
          |
          v
   FastAPI (main.py) v2.5.0
          |
   routers → services → Supabase/PostgreSQL
          |
   Gemini AI (צ'אט)
          |
   Payment adapters (Stripe / PayMe)
          |
   Stripe webhooks
```

### שכבות האפליקציה

- `main.py` — נקודת הכניסה של FastAPI. רושם את כל ה-middleware, הראוטרים, ו-endpoints של health/readiness. מריץ migrations בתהליך רקע בעת הפעלה.
- `backend/routers/` — מטפלי HTTP: auth, onboarding, safe_auth, email_verification, profile, businesses, products, chat, orders, payments, analytics, dashboard, subscription, api_keys, widget, stripe_webhook, frontend.
- `backend/services/` — שירותים: Stripe, PayMe, Gemini AI, email (Resend), sessions, migrations, billing, money, widget_auth, webhook_security, monitoring (Sentry), observability.
- `backend/middleware/` — Supabase Auth bearer-token validation, tenant ownership, rate limiting (Redis + in-memory fallback), correlation IDs, request context.
- `backend/models/schemas.py` — כל מודלי Pydantic. שדות כספיים משתמשים ב-`Decimal`.
- `database/full_schema_bootstrap.sql` — schema בסיסי idempotent.
- `frontend/html/` — כל דפי ה-HTML הסטטיים. `frontend/js/` — סקריפטים צד-לקוח.

ה-API מותקן תחת `/api/v1`. תיעוד OpenAPI זמין רק בסביבות שאינן production (`/docs`, `/redoc`).

---

## זרימת המשתמש

1. **דף נחיתה** — המשתמש מגיע ל-`/` ורואה את `home.html`.
2. **הרשמה** — `POST /api/v1/auth/signup` יוצר משתמש ב-Supabase Auth, פרופיל עם תוכנית `free`, ושולח מייל אימות דרך Resend.
3. **אימות מייל** — `GET /api/v1/auth/verify?token=...` מאמת את הטוקן ומסמן את הפרופיל כמאומת דרך RPC `mark_email_verified`.
4. **התחברות** — `POST /api/v1/auth/login` מחזיר JWT. בהתחברות ראשונה נוצרים פרופיל ועסק ראשוני אוטומטית.
5. **דשבורד חינמי** — המשתמש מקבל דשבורד עם ווידגט מוגבל ל-5 הודעות לשעה לכל session. הבוט מכיר את המוצרים של העסק שלו ויכול לתמחר, אך לא מוציא לינק תשלום (מוגבל לתוכנית חינמית).
6. **שדרוג** — `POST /api/v1/payments/create-checkout-session` פותח Stripe Checkout לרכישת PRO או PREMIUM.
7. **אחרי שדרוג** — המשתמש יכול ליצור API keys ולהטמיע את הווידגט באתר שלו (WordPress, Wix, HTML רגיל) דרך `/setup-guide`.
8. **ווידגט מוטמע** — הצ'אטבוט פועל על אתר הלקוח. כשמשתמש קצה רוצה לקנות, הבוט יוצר הזמנה ומוציא לינק תשלום ישירות בשיחה.

---

## תוכניות מנוי

מוגדרות ב-`backend/routers/dashboard.py`:

| תכונה | free | pro | premium |
|---|---|---|---|
| מוצרים ואנליטיקס | ✓ | ✓ | ✓ |
| הזמנות ומכירות | — | ✓ | ✓ |
| הטמעה (WordPress / HTML) | — | ✓ | ✓ |
| דומיינים מותאמים | — | עד 3 | עד 10 |
| API keys לווידגט | 0 | עד 3 | עד 10 |
| הודעות צ'אט לשעה | 5 | ללא הגבלה | ללא הגבלה |
| תשלום דרך הצ'אט | — | ✓ | ✓ |

---

## ספקי תשלום

הספק הפעיל נקבע על ידי משתנה הסביבה `PAYMENT_PROVIDER` (ברירת מחדל: `stripe`). הפקטורי `get_checkout_adapter()` ב-`backend/services/payment_adapters.py` מחזיר את ה-adapter המתאים.

| ספק | Adapter | הערות |
|---|---|---|
| `stripe` | `StripeCheckoutAdapter` | ברירת מחדל. Stripe Checkout hosted page. |
| `payme` | `PayMeCheckoutAdapter` | PayMe IL. דורש `PAYME_CLIENT_KEY` ו-`PAYME_SELLER_PAYME_ID`. |

### מחזור חיים של הזמנה

1. הצ'אטבוט מזהה כוונת רכישה ויוצר הזמנה ב-`orders`.
2. נוצר checkout session אצל ספק התשלום.
3. לינק התשלום מוחזר ישירות בתשובת הצ'אט.
4. Stripe שולח webhook → `POST /api/v1/webhooks/stripe`.
5. הוידאציה: חתימת Stripe + idempotency דרך `claim_webhook_event` RPC.
6. עדכון אטומי של ההזמנה דרך `update_order_payment_atomic` RPC.

---

## מחסנית Middleware

מוחל בסדר הבא ב-`main.py`:

1. `CorrelationIdMiddleware` — מזריק `X-Correlation-ID` לכל בקשה/תגובה.
2. `AuthRateLimitMiddleware` — rate limiting לפי IP על endpoints של auth.
3. `PublicEndpointSafetyNetMiddleware` — 120 req/min IP backstop לכל ה-public prefixes.
4. `DualCORSMiddleware` — wildcard CORS ל-public endpoints, credentialed CORS לאוריג'ינים מוגדרים.
5. `SecurityHeadersMiddleware` — CSP, HSTS (production), X-Content-Type-Options, X-Frame-Options, COOP, Referrer-Policy, Permissions-Policy.

---

## אבטחה

- אימות JWT דרך Supabase Auth bearer-token (`backend/middleware/auth.py`).
- בדיקות tenant ownership דרך `verify_tenant_ownership` ו-`require_business_owner_for_business_id`.
- RLS policies ב-PostgreSQL לכל הטבלאות הרגישות.
- אימות חתימת Stripe webhook + הגנה מפני replay דרך `webhook_events` + `claim_webhook_event`.
- Rate limiting: per-endpoint (chat, widget config), per-auth-endpoint, ו-IP safety net. Redis-backed עם in-memory fallback.
- API keys מאוחסנים כ-HMAC-SHA256 hashes.
- ווידגט חינמי מוגבל ל-5 הודעות לשעה לכל session_id.
- Origin/Referer headers לא משמשים לשום החלטת אבטחה.

---

## פיתוח מקומי

### דרישות מוקדמות

- Python 3.12 מומלץ (Dockerfile משתמש ב-3.11-slim).
- פרויקט Supabase עם PostgreSQL connection string.
- Stripe test credentials לפיתוח checkout ו-webhooks.

### התקנה

```bash
git clone https://github.com/Ari-tech-abc/ConversaPay.git
cd ConversaPay
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

מלא את `.env` עם credentials לפיתוח, ואז הפעל:

```bash
uvicorn main:app --reload
```

### Endpoints שימושיים

| Endpoint | תיאור |
|---|---|
| `GET /health` | liveness — 503 אם migrations ממתינים |
| `GET /ready` | readiness — בדיקת DB ו-Redis |
| `GET /api/v1/config/public` | מחזיר `supabase_url` ו-`supabase_anon_key` |
| `GET /docs` | OpenAPI UI (לא-production בלבד) |

---

## משתני סביבה

### חובה

| משתנה | תיאור |
|---|---|
| `SECRET_KEY` | מפתח HMAC/הצפנה של האפליקציה |
| `SUPABASE_URL` | URL של פרויקט Supabase |
| `SUPABASE_ANON_KEY` | מפתח Supabase ציבורי |
| `SUPABASE_SERVICE_ROLE_KEY` | מפתח service-role — לעולם לא לחשוף |
| `GEMINI_API_KEY` | credential של Gemini AI |
| `RESEND_API_KEY` | credential של ספק המייל |
| `EMAIL_FROM_ADDRESS` | כתובת שולח למיילים transactional |

### DB ו-Runtime

| משתנה | תיאור |
|---|---|
| `DATABASE_URL` | PostgreSQL connection לreadiness ו-migrations |
| `REDIS_URL` | אופציונלי — Redis לrate limiting מבוזר |
| `MIGRATIONS_AUTO_APPLY` | הפעלת migrations אוטומטיים בהפעלה (ברירת מחדל: `true`) |
| `ENVIRONMENT` | `development`, `test`, או `production` |
| `DEBUG` | חייב להיות `false` ב-production |
| `API_PREFIX` | prefix של ה-API, ברירת מחדל `/api/v1` |
| `CORS_ORIGINS` | אוריג'ינים מורשים מופרדים בפסיק |
| `PAYMENT_PROVIDER` | `stripe` (ברירת מחדל) או `payme` |

### URLs ואינטגרציות

| משתנה | תיאור |
|---|---|
| `BASE_URL` | URL קנוני של האפליקציה |
| `FRONTEND_URL` | URL של הפרונטאנד |
| `BACKEND_URL` | URL של הבקאנד |
| `STRIPE_SECRET_KEY` | מפתח Stripe API — server-only |
| `STRIPE_WEBHOOK_SECRET` | secret לאימות חתימת Stripe |
| `STRIPE_PRO_PRICE_ID` | Stripe Price ID לתוכנית PRO |
| `STRIPE_PREMIUM_PRICE_ID` | Stripe Price ID לתוכנית PREMIUM |
| `STRIPE_SUCCESS_URL` | URL הצלחה אחרי תשלום |
| `STRIPE_CANCEL_URL` | URL ביטול תשלום |
| `PAYME_CLIENT_KEY` | מפתח PayMe client |
| `PAYME_SELLER_PAYME_ID` | PayMe seller ID |
| `PAYME_API_BASE_URL` | ברירת מחדל: `https://sandbox.payme.io` |
| `PAYME_SUCCESS_URL` | URL הצלחה PayMe |
| `PAYME_CANCEL_URL` | URL ביטול PayMe |
| `PAYME_CALLBACK_URL` | אופציונלי — PayMe server callback |
| `SENTRY_DSN` | אופציונלי — Sentry DSN לtracking שגיאות |

---

## בסיס נתונים

### Schema

הגדרת הבסיס נמצאת ב-`database/full_schema_bootstrap.sql`. הקובץ idempotent — שומר על נתונים קיימים.

### טבלאות מרכזיות

| טבלה | תיאור |
|---|---|
| `profiles` | פרופיל משתמש, תוכנית מנוי, מצב אימות מייל |
| `businesses` | עסקים של המשתמשים |
| `products` | קטלוג מוצרים לכל עסק |
| `customers` | לקוחות שיצרו קשר דרך הווידגט |
| `conversations` | שיחות צ'אט לפי session |
| `messages` | הודעות בתוך שיחה |
| `orders` | הזמנות שנוצרו מהצ'אט |
| `payments` | תשלומים לפי הזמנה |
| `api_keys` | API keys לווידגט (PRO/PREMIUM) |
| `webhook_events` | idempotency לאירועי Stripe |

### פונקציות DB

| פונקציה | תיאור |
|---|---|
| `user_owns_business` | helper לRLS — בדיקת בעלות |
| `mark_email_verified` | מסמן מייל כמאומת (SECURITY DEFINER) |
| `claim_webhook_event` | idempotency לwebhooks |
| `update_order_payment_atomic` | עדכון אטומי של הזמנה + תשלום |
| `consume_site_lead_rate_limit` | rate limiting transactional |
| `get_user_analytics_overview` | RPC לאנליטיקס מצטבר |

### Migrations

migrations מצטברים נמצאים ב-`database/migrations/` ומוחלים לפי סדר שם הקובץ. ה-migration runner רושם כל migration עם SHA-256 checksum ב-`public.schema_migrations`. נעילת `pg_advisory_xact_lock` מונעת ריצות מקבילות.

---

## פריסה

### Render.com

הפריסה מוגדרת ב-`render.yaml`. Health check path: `/ready`.

```bash
# start command
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Docker

Multi-stage build עם Python 3.11-slim, משתמש non-root `appuser`.

```bash
docker build -t talk2pay .
docker run -p 8000:8000 --env-file .env talk2pay
```

---

## מבנה הריפו

```
backend/
  middleware/       Auth, tenant guards, rate limits, correlation IDs
  models/           Pydantic schemas (schemas.py)
  routers/          FastAPI route handlers (16 קבצים)
  services/         Stripe, PayMe, Gemini, sessions, migrations, billing,
                    money, product search, widget auth, webhook security,
                    email, monitoring, observability
  static/           robots.txt, sitemap.xml
  config.py         הגדרות מרכזיות דרך pydantic-settings
  dependencies.py   Supabase client providers (לא בשימוש מלא)
database/
  full_schema_bootstrap.sql
  migrations/       SQL migrations מצטברים
docs/
  infra/            הערות תשתית לפי שלבים
  API.md            תיעוד endpoints
frontend/
  html/             דפי HTML של האפליקציה + conversapay-ui.css
  js/               dashboard, widget, onboarding, email-guard scripts
wordpress-plugin/   פלאגין WordPress לווידגט הצ'אט (PHP)
main.py             נקודת כניסה של FastAPI (v2.5.0)
render.yaml         הגדרת פריסה ל-Render.com
Dockerfile          Multi-stage Docker build
requirements.txt    תלויות Python
```

---

## בעיות ידועות

- `backend/services/product_service.py` מממש חיפוש מוצרים מבוסס keywords אך לא מיובא על ידי אף ראוטר. ראוטר הצ'אט מבצע שאילתות ישירות ל-Supabase.
- `Dockerfile.txt` ו-`gitignore.txt` הם עותקים טקסטואליים של `Dockerfile` ו-`.gitignore` — artifacts ישנים.
- drift בגרסה: `backend/__init__.py` מצהיר `__version__ = "2.0.0"` בעוד `main.py` מצהיר `version="2.5.0"`. הגרסה הסמכותית היא `2.5.0`.
- רוב הראוטרים יוצרים instance של `create_client()` ברמת המודול במקום להשתמש ב-dependency injection מ-`backend/dependencies.py`. המעבר לתבנית זו לא הושלם.
