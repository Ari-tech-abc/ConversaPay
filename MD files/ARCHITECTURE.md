# Talk2Pay, Production Architecture

## Overview

Talk2Pay היא מערכת מסחר שיחתי רב-שוכרת. היא מחברת AI, קטלוג, הזמנות, תשלומים, ווידג׳ט, WhatsApp ואנליטיקות למערכת אחת.

הדומיין `conversapay.org` וה-prefixes הטכניים `conversapay` נשארים ללא שינוי מסיבות תאימות. המותג הציבורי, כותרות המוצר, הודעות המשתמש, המיילים, מסמכי השיווק והנגישות הם Talk2Pay.

## Runtime

```text
Browser / WordPress / WhatsApp
            |
            v
      FastAPI + Uvicorn
            |
  Auth, tenant checks, rate limits, webhooks
            |
          Supabase
            |
  PayMe / Stripe / Gemini / Resend / Meta
```

## שכבות המערכת

### Backend

- `main.py` מנהל את האפליקציה, הראוטים, headers, CORS, health ו-delivery branding.
- `backend/routers/` מכיל auth, businesses, products, chat, orders, payments, analytics, widget, dashboard, profile, subscription, admin ו-Site Builder.
- `backend/services/` מכיל אינטגרציות תשלום, AI, אימייל, sessions, monitoring ו-observability.
- `backend/middleware/` מטפל באימות, correlation IDs והגנות בקשה.

### Frontend

- `frontend/html/` מכיל את המסכים הציבוריים והמאומתים.
- `frontend/js/widget.js` הוא הווידג׳ט להטמעה. ה-ID הפנימי `conversapay-chat-widget` נשמר לתאימות.
- `conversapay-site-builder/frontend/` הוא מסלול תאימות קיים עבור ממשק Site Builder, בעוד שהמותג שמוצג למשתמש הוא Talk2Pay.
- `wordpress-plugin/conversapay-chat.php` נשאר בשם הקובץ הישן כדי לא לשבור התקנות קיימות.

## זרימת ליד

1. אתר שנוצר ב-Site Builder שולח טופס עם עסק, שם, אימייל, חברה והודעה.
2. שדה honeypot נפרד מסנן בוטים בלי לזרוק לידים שמילאו חברה.
3. Origin נבדק מול origins מוגדרים ודומיינים מותאמים לעסק.
4. rate limit אטומי נצרך ב-Postgres לפי עסק ו-IP מגובב.
5. הליד נשמר בטבלת `lead_submissions` עם RLS ובידוד לפי business.
6. בעל העסק רואה את הפניות דרך `/leads` ומעדכן סטטוס.

## נתונים ואבטחה

- כל טבלה עסקית חייבת להישאר tenant-scoped.
- `lead_submissions` מאפשרת קריאה, עדכון ומחיקה לבעל העסק בלבד דרך RLS.
- `site_lead_rate_limits` חסומה מ-anon ו-authenticated, והפונקציה ניתנת להרצה רק ל-service role.
- secrets, service-role keys, Stripe secrets ו-WhatsApp access tokens אינם חלק מה-frontend הציבורי.
- Webhooks חייבים חתימה ואימות replay לפי ספק.

## Deployment

Render מריץ את `main` עם Uvicorn. `render.yaml` מגדיר `autoDeployTrigger: commit` ו-health check על `/ready`. `production-smoke.yml` בודק שה-host החי מגיש את release marker, Talk2Pay, המחירים המעודכנים וללא מיתוג ישן.

## Compatibility boundary

אין לשנות את `conversapay.org`, routes, environment variables, API identifiers, table names, RLS function names, DOM roots או filenames ללא migration, aliases, בדיקות rollback ותיאום deployment.

## Quality bar

CI חייב להעביר compile, quality gate, local link validation וכל test suite. אישור production דורש בנוסף migration applied, browser matrix ב-320, 375, 768, 1024 ו-1440 פיקסלים, בדיקות תשלומים, OAuth, ווידג׳ט, Site Builder ותרחישי tenant isolation.
