# ConversaPay - Multi-Tenant SaaS Platform

פלטפורמת SaaS רב-שוכרת (Multi-Tenant) לסוכני מכירות ושירות לקוחות אוטונומיים מבוססי בינה מלאכותית.

## 🚀 תכונות עיקריות

### Backend
- **ארכיטקטורה מודולרית**: ארגון מחדש מלא עם FastAPI, פונקציות אסינכרוניות, וטיפוסים מלאים
- **אימות מבוסס Supabase Auth**: הרשמה, התחברות, התנתקות ושחזור סיסמה
- **רב-שוכרות מלאה (Multi-Tenancy)**: בידוד נתונים מלא באמצעות Row Level Security (RLS)
- **AI מתקדם עם Gemini**: שיחות עם הקשר מורחב (היסטוריה, קטלוג, לקוח)
- **תשלומים אמיתיים עם Stripe**: אינטגרציה מלאה עם Stripe Checkout ו-Webhooks
- **ניהול מוצרים והזמנות**: CRUD מלא, מעקב אחר הזמנות וסטטוסים
- **דשבורד מתקדם עם אנליטיקות**: סטטיסטיקות בזמן אמת, ניהול עסק, מוצרים, הזמנות ושיחות
- **התראות במייל**: שליחת קבלות, אישורי הזמנה והודעות ברוכים הבאים
- **ניטור ולוגים**: אינטגרציה עם Sentry, לוגים מרכזיים
- **Webhooks**: תשתית לוואטסאפ, טלגרם ואינטגרציות חיצוניות
- **ווידג'ט צף**: הטמעה קלה בכל אתר עם שורת קוד אחת

### Frontend
- **עיצוב מודרני ורספונסיבי**: תמיכה מלאה ב-RTL, עיצוב נקי ומקצועי
- **דשבורד מתקדם עם אנליטיקות**: 
  - כרטיסי KPI (הכנסות, שיעור המרה, AOV, סשנים)
  - גרפים אינטראקטיביים (Chart.js) - הכנסות יומיות והזמנות לפי סטטוס
  - טבלת מוצרים נמכרים
  - תמיכה בתקופות 7/30/90 ימים
- **צ'אט חכם עם תשלום**: ממשק צ'אט יפה עם תשלום ישיר וסטטוס בזמן אמת
- **ווידג'ט להטמעה**: קובץ JS עצמאי להטמעה בכל אתר

## 📁 מבנה הפרויקט

```
conversapay-backend/
├── backend/
│   ├── __init__.py
│   ├── config.py                 # הגדרות וקונפיגורציה
│   ├── middleware/
│   │   └── auth.py              # אמצעי אימות JWT
│   ├── models/
│   │   └── schemas.py           # Pydantic schemas עם טיפוסים מלאים
│   ├── routers/
│   │   ├── auth.py              # הרשמה, התחברות, התנתקות
│   │   ├── businesses.py        # ניהול עסקים
│   │   ├── products.py          # ניהול מוצרים
│   │   ├── chat.py              # צ'אט עם AI
│   │   ├── orders.py            # ניהול הזמנות
│   │   ├── payments.py          # תשלומים ו-Stripe
│   │   ├── analytics.py         # אנליטיקות ודוחות
│   │   ├── logs.py              # לוגים
│   │   └── webhooks.py          # Webhooks (WhatsApp, Telegram)
│   ├── services/
│   │   ├── gemini_service.py    # שירות Gemini AI
│   │   ├── payment_service.py   # שירות תשלומים
│   │   ├── session_service.py   # ניהול סשנים ושיחות
│   │   ├── email_service.py     # שליחת מיילים
│   │   └── monitoring_service.py # ניטור ולוגים
│   ├── templates/               # 📁 תבניות PHP (WordPress plugin)
│   │   └── conversapay-chat.php # תבנית פלאגין וורדפרס
│   └── static/                  # 📁 קבצים סטטיים ציבוריים
│       └── js/
│           └── widget.js        # ווידג'ט צף (מוגן לשרת ציבורי)
├── database/
│   ├── schema.sql               # סכמת מסד הנתונים
│   ├── rls_policies.sql         # מדיניות אבטחה RLS
│   └── seed.sql                 # נתוני בדיקה
├── frontend/
│   ├── css/
│   │   └── main.css             # עיצוב מרכזי
│   └── js/
│       ├── widget.js            # ווידג'ט צף לאתרים (מקור)
│       └── dashboard.js         # לוגיקת דשבורד ואנליטיקות
├── main.py                      # נקודת כניסה ראשית
├── requirements.txt              # תלויות Python
├── .env.example                  # דוגמה למשתני סביבה
├── dashboard.html                # דף דשבורד עם אנליטיקות
├── index.html                    # דף צ'אט
├── pay.html                      # דף תשלום
└── home.html                     # דף בית
```

## 🛠️ התקנה והגדרה

### דרישות מקדימות

- Python 3.9+
- PostgreSQL (דרך Supabase)
- חשבון Supabase
- מפתחות API: Gemini, Stripe, Resend (אופציונלי)

### שלב 1: שכפול הפרויקט

```bash
git clone <repository-url>
cd conversapay-backend
```

### שלב 2: הגדרת משתני סביבה

```bash
# העתק את קובץ הדוגמה
cp .env.example .env

# ערוך את הקובץ עם הערכים שלך
nano .env
```

### שלב 3: התקנת תלויות

```bash
pip install -r requirements.txt
```

### שלב 4: הגדרת Supabase

1. צור פרויקט חדש ב-[Supabase](https://supabase.com)
2. הפעל את PostgreSQL
3. העתק את כתובת הפרויקט ומפתחות ה-API ל-`.env`
4. הפעל את האימות בפרויקט Supabase שלך (Authentication → Settings)

### שלב 5: יצירת סכמת מסד הנתונים

1. פתח את Supabase Dashboard
2. לך ל-SQL Editor
3. העתק והפעל את הקבצים הבאים בסדר:
   - `database/schema.sql`
   - `database/rls_policies.sql`
   - `database/seed.sql` (אופציונלי - לנתוני בדיקה)

### שלב 6: הגדרת אימות Supabase

1. ב-Supabase Dashboard, לך ל-Authentication → Providers
2. הפעל Email provider
3. הגדר את כתובת המייל למשלוח אימותים (אופציונלי)
4. העתק את ה-Anon Key וה-Service Role Key ל-`.env`

### שלב 7: הגדרת Stripe

1. צור חשבון ב-[Stripe](https://stripe.com)
2. קבל את מפתח ה-API (Secret Key)
3. הגדר Webhook endpoint:
   - URL: `https://your-domain.com/api/v1/payments/webhook`
   - אירועים: `checkout.session.completed`, `invoice.payment_succeeded`, `customer.subscription.deleted`
4. העתק את מפתח ה-API וה-Webhook Secret ל-`.env`

### שלב 8: הגדרת Gemini AI

1. צור פרויקט ב-[Google AI Studio](https://aistudio.google.com)
2. קבל מפתח API ל-Gemini
3. העתק את המפתח ל-`.env`

### שלב 9: הפעלת השרת

```bash
# פיתוח
python main.py

# או עם uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

השרת יהיה זמין בכתובת: `http://localhost:8000`

## 📚 תיעוד API

### מסמכים אוטומטיים

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### נקודות קצה עיקריות

#### אימות
- `POST /api/v1/auth/register` - הרשמה
- `POST /api/v1/auth/login` - התחברות
- `POST /api/v1/auth/logout` - התנתקות
- `POST /api/v1/auth/password-reset/request` - בקשת איפוס סיסמה
- `GET /api/v1/auth/me` - מידע על המשתמש המחובר

#### עסקים
- `POST /api/v1/businesses` - יצירת עסק
- `GET /api/v1/businesses` - רשימת עסקים
- `GET /api/v1/businesses/{business_id}` - פרטי עסק
- `PATCH /api/v1/businesses/{business_id}` - עדכון עסק
- `DELETE /api/v1/businesses/{business_id}` - מחיקת עסק
- `GET /api/v1/businesses/{business_id}/stats` - סטטיסטיקות

#### אנליטיקות
- `GET /api/v1/analytics/businesses/{business_id}/analytics` - דשבורד אנליטיקות מלא
- `GET /api/v1/analytics/businesses/{business_id}/revenue?days=30` - הכנסות לפי ימים
- `GET /api/v1/analytics/businesses/{business_id}/orders?days=30` - הזמנות לפי ימים

#### מוצרים
- `POST /api/v1/products` - יצירת מוצר
- `GET /api/v1/products?business_id={id}` - רשימת מוצרים
- `GET /api/v1/products/{product_id}` - פרטי מוצר
- `PATCH /api/v1/products/{product_id}` - עדכון מוצר
- `DELETE /api/v1/products/{product_id}` - מחיקת מוצר
- `GET /api/v1/products/business/{business_id}/public` - מוצרים ציבוריים (ללא אימות)

#### צ'אט
- `POST /api/v1/chat` - שליחת הודעה ל-AI (ציבורי)
- `GET /api/v1/chat/conversations/{id}/history` - היסטוריית שיחה (מאומת)

#### הזמנות
- `POST /api/v1/orders` - יצירת הזמנה
- `GET /api/v1/orders?business_id={id}` - רשימת הזמנות
- `GET /api/v1/orders/{id}` - פרטי הזמנה
- `PATCH /api/v1/orders/{id}` - עדכון הזמנה
- `GET /api/v1/orders/{id}/status` - סטטוס הזמנה (ציבורי - לפליטינג)
- `GET /api/v1/orders/{id}/summary` - סיכום הזמנה (ציבורי)

#### תשלומים
- `POST /api/v1/payments/create-checkout-session` - יצירת סשן מנוי Pro
- `POST /api/v1/payments/checkout-session` - יצירת סשן תשלום
- `GET /api/v1/payments/success` - דף הצלחת תשלום
- `GET /api/v1/payments/canceled` - דף ביטול תשלום
- `GET /api/v1/payments/wordpress-plugin/{business_id}` - הורדת פלאגין וורדפרס
- `POST /api/v1/payments/webhook` - Webhook של Stripe

#### לוגים
- `GET /api/v1/logs` - צפייה בלוגים
- `GET /api/v1/logs/stats` - סטטיסטיקות לוגים

#### Webhooks
- `POST /api/v1/webhooks` - יצירת webhook
- `GET /api/v1/webhooks?business_id={id}` - רשימת webhooks
- `POST /api/v1/webhooks/whatsapp/{business_id}` - Webhook של WhatsApp
- `POST /api/v1/webhooks/telegram/{business_id}` - Webhook של Telegram

## 🔒 אבטחה

### אימות והרשאות
- כל הבקשות המאומתות דורשות אסימון JWT ב-Header: `Authorization: Bearer {token}`
- שימוש ב-Supabase Auth לאימות משתמשים
- מדיניות RLS במסד הנתונים לבידוד רב-שוכרת
- הגנת שדה מנוי עם PostgreSQL triggers

### הגדרות אבטחה
- הסתרת מפתחות API במשתני סביבה
- שימוש ב-HTTPS בפרודקשן
- Webhook signatures לאימות מקור
- הגבלת CORS למיקומים מורשים
- ווידג'ט צף נגיש ציבורי עם CORS מותנה

## 🚢 פריסה (Deployment)

### Docker (מומלץ)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Build
docker build -t conversapay-backend .

# Run
docker run -p 8000:8000 --env-file .env conversapay-backend
```

### Railway

1. חבר את הפרויקט ל-Railway
2. הגדר משתני סביבה ב-Railway Dashboard
3. הפרויקט יפרוס אוטומטית

### Render

1. צור Web Service חדש ב-Render
2. חבר Git Repository
3. הגדר:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. הוסף משתני סביבה

### Vercel / Netlify

השתמש ב-Docker container או בשרת פנימי (Serverless Function).

## 🧪 בדיקות

```bash
# הרצת בדיקות (כשיהיו)
pytest

# בדיקות עם כיסוי
pytest --cov=backend --cov-report=html
```

## 📊 ניטור

### Sentry
הגדר `SENTRY_DSN` ב-`.env` כדי להפעיל ניטור שגיאות.

### לוגים
כל השגיאות והאזהרות נשמרות במסד הנתונים בטבלת `logs` וניתנות לצפייה דרך הדשבורד.

## 🤝 תרומה

1. Fork את הפרויקט
2. צור branch חדש (`git checkout -b feature/amazing-feature`)
3. Commit את השינויים (`git commit -m 'Add amazing feature'`)
4. Push ל-branch (`git push origin feature/amazing-feature`)
5. פתח Pull Request

## 📄 רישיון

פרויקט זה מוגן תחת רישיון MIT. ראה קובץ `LICENSE` לפרטים נוספים.

## 📞 תמיכה

לשאלות ותמיכה, פנה ל:
- Email: support@conversapay.org
- Documentation: [docs.conversapay.org](https://docs.conversapay.org)

## 🗺️ מפת דרכים

- [x] ארכיטקטורה מודולרית
- [x] אימות Supabase Auth
- [x] רב-שוכרות עם RLS
- [x] אינטגרציית Stripe
- [x] שירות Gemini AI מורחב
- [x] דשבורד עם אנליטיקות
- [x] ווידג'ט צף עם תשלום בזמן אמת
- [x] התראות במייל
- [x] ניטור ולוגים
- [x] Webhooks (WhatsApp, Telegram)
- [ ] בדיקות יחידה ואינטגרציה
- [ ] תמיכה בשפות נוספות
- [ ] אפליקציית מובייל
- [ ] שיתוף פעולה צוותי

---

**נבנה עם ❤️ על ידי צוות ConversaPay**