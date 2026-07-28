# Talk2Pay site audit report

## Scope

הדוח מתייחס לדף הבית, מסכי auth, dashboard, billing, widget, Site Builder, WordPress, תשלום, legal והודעות שגיאה.

## Brand decision

Talk2Pay הוא השם הציבורי הרשמי. `conversapay.org` נשאר domain תשתיתי בלבד. identifiers כמו `CONVERSAPAY_*`, `conversapay_chat_settings`, `conversapay-chat-widget` ושמות קבצים נשמרים לתאימות.

## Current controls

- כל המסכים המוגשים דרך FastAPI עוברים delivery normalization ל-Talk2Pay.
- login, pay, 404, leads, widget demo ו-Site Builder משתמשים ב-Talk2Pay במקור או בגבול ההגשה.
- המותג נשמר עקבי בכותרות, alt text, labels, emails, הודעות widget ומסמכי המוצר.
- mobile ו-desktop מקבלים אותו hierarchy, focus states ו-reduced-motion behavior.

## Remaining evidence gates

- visual regression מלא בדפדפנים ובגדלי 320, 375, 768, 1024 ו-1440.
- בדיקת נגישות עם keyboard ו-screen reader.
- smoke test של כל מסלול תשלום, OAuth, ווידג׳ט, Site Builder ולידים.
- אימות שהאתר החי מגיש את אותו commit מ-main.

## Conclusion

המוצר הציבורי הוא Talk2Pay. legacy names שנותרו בקוד אינם brand drift כאשר הם מופיעים רק בתוך compatibility boundary מתועד.
