# Talk2Pay system audit

## Brand and compatibility

Talk2Pay הוא המותג הרשמי. הדומיין `conversapay.org`, route names, environment variables, API identifiers, database names, RLS functions, DOM roots ושמות קבצים נשמרים ללא שינוי כדי למנוע שבירת לקוחות קיימים.

## Runtime controls

- FastAPI ו-Uvicorn בפרודקשן.
- `/ready` מחזיר `status=ready` ו-`environment=production` כאשר השירות זמין.
- CI מריץ compile, quality gate, local link validation ו-pytest.
- Render מוגדר ל-auto deploy מ-main ול-health check.
- Production smoke בודק Talk2Pay, release marker והיעדר מחירים ישנים.

## Security controls

- Supabase Auth ו-JWT.
- RLS ובידוד tenant.
- Webhook signatures ו-replay protection.
- Origin validation ו-rate limiting אטומי לטפסי Site Builder.
- שדה חברה גלוי ושדה honeypot נפרד.

## Honest status

הקוד והמיתוג ב-main עברו את סבב ההקשחות. ציון production סופי מחייב גם ראיות environment-level: migration applied, browser matrix, E2E payments, widget smoke, lead persistence ו-deploy verification.
