# Talk2Pay, Multi-Tenant SaaS Platform

Talk2Pay היא פלטפורמת מסחר שיחתי רב-שוכרת לעסקים: שיחה, קטלוג, המלצת מוצר, הזמנה ותשלום באותו רצף.

הדומיין `conversapay.org`, שמות הקבצים, מזהי ה-API, שמות טבלאות, מפתחות אחסון ונתיבי deployment נשמרים בכוונה לצורך תאימות תשתיתית. הם אינם השם הציבורי של המוצר.

## מה יש במוצר

- צ׳אט AI שמכיר את הקטלוג, המחירים והמלאי.
- ניהול עסקים, מוצרים, הזמנות, לקוחות ואנליטיקות.
- תשלומים ומנויים דרך ספקי הסליקה הנתמכים.
- ווידג׳ט JavaScript להטמעה באתר ו-WordPress.
- WhatsApp Business לעסקים במסלול המתאים.
- Site Builder מבוסס AI עם תצוגה מקדימה ועריכה ויזואלית.
- תיבת פניות עם בידוד לפי עסק, RLS, סטטוסים והגנת rate limit.

## מבנה הפרויקט

```text
conversapay-project/
├── backend/                 # FastAPI, auth, businesses, products, chat, orders, payments
├── database/                # schema and migrations, including RLS
├── frontend/                # HTML, CSS and JavaScript product surfaces
├── conversapay-site-builder/ # Site Builder package and compatibility path
├── wordpress-plugin/        # WordPress integration, compatibility filename retained
├── tests/                   # backend, security and product contract tests
├── main.py                  # FastAPI application entry point
└── render.yaml              # Render deployment configuration
```

## הפעלה מקומית

```bash
cp .env.example .env
pip install -r requirements.txt
python main.py
```

## בדיקות

```bash
python scripts/ui_quality_gate.py
python scripts/check_html_links.py
python -m pytest -q
```

## נתיבי מוצר מרכזיים

- `/` דף הבית של Talk2Pay.
- `/login` ו-`/register` כניסה והרשמה.
- `/dashboard` ניהול העסק.
- `/leads` תיבת פניות נכנסות.
- `/setup-guide` מדריך הטמעה.
- `/widget-demo` סביבת בדיקה לווידג׳ט.
- `/site-builder` בונה האתרים.

## אבטחה ותאימות

- Supabase Auth ו-JWT למסלולים מאומתים.
- Row Level Security לבידוד בין עסקים.
- חתימות Webhook, CORS מותאם ומפתחות API מוצפנים או מגובבים לפי השימוש.
- rate limit אטומי לפניות ציבוריות, לפי עסק ו-IP מגובב.
- Origin חובה לטפסי Site Builder, מול דומיינים מורשים.
- אין לשנות שמות `CONVERSAPAY_*`, routes, שמות קבצים או identifiers בלי migration ותוכנית rollback.

## סטטוס

הקוד ב-main הוא מקור האמת. לפני הצגת המוצר ללקוח enterprise יש להריץ CI, להחיל migrations בסביבת staging, לבצע browser smoke test בכל רוחבי המסך, ולאמת שה-deploy החי מגיש את אותו commit.

**Talk2Pay, built for the moment a conversation becomes a transaction.**
