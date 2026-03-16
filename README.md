# 🏠 דירה-האנטר — מערכת סריקת דירות אוטומטית
# Apartment Hunter — Automated Rental Apartment Scanner

## מה זה עושה?
סורק דירות להשכרה ביד2 כל 10 דקות ושולח התראה מיידית ב-Telegram
עם כל הפרטים + כפתור ליצירת קשר ישירה.

## עלות: ₪0 (חינם לגמרי)

---

## 🚀 התקנה מהירה (10 דקות)

### שלב 1: יצירת Telegram Bot

1. פתח Telegram וחפש את `@BotFather`
2. שלח `/newbot`
3. תן שם לבוט (למשל: `DiraHunterBot`)
4. תקבל **Bot Token** — שמור אותו!
5. פתח את הבוט ושלח הודעה כלשהי (למשל "hi")
6. גלוש ל: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
7. מצא את ה-`chat_id` שלך בתשובה — שמור אותו!

### שלב 2: העלאה ל-GitHub

1. צור Repository חדש ב-GitHub (פרטי)
2. העלה את כל הקבצים מהתיקייה הזו
3. לך ל-Settings → Secrets and variables → Actions
4. הוסף את ה-Secrets הבאים:
   - `TELEGRAM_BOT_TOKEN` — הטוקן מ-BotFather
   - `TELEGRAM_CHAT_ID` — ה-chat_id שלך

### שלב 3: הגדרת הפילטרים

ערוך את הקובץ `config.json` לפי מה שאתה מחפש:
- טווח מחירים
- מספר חדרים  
- אזורים/שכונות
- מילות מפתח

### שלב 4: הפעלה

Push ל-GitHub וה-Action ירוץ אוטומטית כל 10 דקות!

---

## 📁 מבנה הקבצים

```
apartment-hunter/
├── README.md              ← אתה כאן
├── config.json            ← הגדרות חיפוש
├── scraper.py             ← סורק יד2
├── telegram_bot.py        ← שליחת התראות
├── analyzer.py            ← ניתוח AI (אופציונלי)
├── db.py                  ← מסד נתונים מקומי
├── main.py                ← הסקריפט הראשי
├── requirements.txt       ← ספריות Python
└── .github/
    └── workflows/
        └── scan.yml       ← GitHub Actions scheduler
```

---

## 📱 דוגמת התראה ב-Telegram

```
🏠 דירה חדשה נמצאה!

📍 פלורנטין, רח׳ וולפסון 12
🛏 3 חדרים | 75 מ״ר | קומה 2
💰 ₪5,500 לחודש
📝 דירה מרווחת ומוארת, משופצת

⏰ עלתה לפני: 3 דקות
📊 ציון התאמה: 92/100

📞 [חייג עכשיו] [פתח ביד2]
```
