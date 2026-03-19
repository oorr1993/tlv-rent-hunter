"""
דירה-האנטר — Main Script
תומך בפקודות טלגרם לשינוי פילטרים בזמן אמת
"""
import json
import os
import sys
import logging
import time
import requests
from pathlib import Path
from datetime import datetime
from scraper import Yad2Scraper
from analyzer import ApartmentScorer
from telegram_bot import TelegramNotifier
from db import ApartmentDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("apartment-hunter")

CONFIG_PATH = Path(__file__).parent / "config.json"
OFFSET_PATH = Path(__file__).parent / "tg_offset.txt"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_env_or_fail(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        logger.error(f"Missing env var: {key}")
        sys.exit(1)
    return value


def get_tg_offset() -> int:
    try:
        if OFFSET_PATH.exists():
            return int(OFFSET_PATH.read_text().strip())
    except Exception:
        pass
    return 0


def save_tg_offset(offset: int):
    OFFSET_PATH.write_text(str(offset))


def process_telegram_commands(token: str, chat_id: str, config: dict) -> dict:
    """
    קורא הודעות חדשות מהבוט ומעדכן config בהתאם.
    פקודות נתמכות:
      /חוף 1.5    - דירות עד 1.5 ק'מ מהחוף
      /חוף כבוי   - בטל פילטר חוף (חזור לשכונות)
      /מחיר 5000 8000  - שנה טווח מחיר
      /חדרים 2 4  - שנה טווח חדרים
      /סטטוס      - שלח סטטוס נוכחי
    """
    base_url = f"https://api.telegram.org/bot{token}"
    offset = get_tg_offset()
    changed = False

    try:
        r = requests.get(f"{base_url}/getUpdates",
            params={"offset": offset, "timeout": 3, "limit": 10},
            timeout=10)
        if r.status_code != 200:
            return config
        updates = r.json().get("result", [])
        if not updates:
            return config

        for update in updates:
            update_id = update["update_id"]
            msg = update.get("message", {})
            text = msg.get("text", "").strip()
            from_id = str(msg.get("from", {}).get("id", ""))

            # Only respond to the authorized chat
            if str(msg.get("chat", {}).get("id", "")) != str(chat_id):
                save_tg_offset(update_id + 1)
                continue

            logger.info(f"Received command: {text}")

            if text.startswith("/חוף") or text.lower().startswith("/beach"):
                parts = text.split()
                if len(parts) >= 2:
                    arg = parts[1].replace(",", ".").strip()
                    if arg in ["כבוי", "off", "0", "no"]:
                        config["search"]["max_distance_from_beach_km"] = 0
                        reply = "✅ פילטר חוף בוטל - חוזר לסריקה לפי שכונות"
                    else:
                        try:
                            km = float(arg)
                            config["search"]["max_distance_from_beach_km"] = km
                            reply = f"✅ מחפש דירות עד {km} ק'מ מהחוף"
                        except ValueError:
                            reply = "❌ שגיאה: /חוף 1.5 (מספר בק'מ)"
                else:
                    reply = "📍 שימוש: /חוף 1.5 (מרחק בק'מ מהחוף)\n/חוף כבוי לביטול"
                changed = True

            elif text.startswith("/מחיר") or text.lower().startswith("/price"):
                parts = text.split()
                if len(parts) >= 3:
                    try:
                        mn = int(parts[1])
                        mx = int(parts[2])
                        config["search"]["min_price"] = mn
                        config["search"]["max_price"] = mx
                        reply = f"✅ מחיר עודכן: ₪{mn:,} - ₪{mx:,}"
                        changed = True
                    except ValueError:
                        reply = "❌ שגיאה: /מחיר 5000 8000"
                else:
                    reply = "📍 שימוש: /מחיר 5000 8000"

            elif text.startswith("/חדרים") or text.lower().startswith("/rooms"):
                parts = text.split()
                if len(parts) >= 3:
                    try:
                        mn = float(parts[1])
                        mx = float(parts[2])
                        config["search"]["min_rooms"] = mn
                        config["search"]["max_rooms"] = mx
                        reply = f"✅ חדרים עודכן: {mn} - {mx}"
                        changed = True
                    except ValueError:
                        reply = "❌ שגיאה: /חדרים 2 4"
                else:
                    reply = "📍 שימוש: /חדרים 2 4"

            elif text.startswith("/סטטוס") or text.lower().startswith("/status"):
                s = config["search"]
                beach = s.get("max_distance_from_beach_km", 0)
                beach_txt = f"{beach} ק'מ מהחוף" if beach else "לפי שכונות"
                reply = (
                    f"📊 סטטוס נוכחי:\n"
                    f"💰 מחיר: ₪{s['min_price']:,} - ₪{s['max_price']:,}\n"
                    f"🛏 חדרים: {s['min_rooms']} - {s['max_rooms']}\n"
                    f"📍 אזור: {beach_txt}"
                )

            elif text.startswith("/עזרה") or text.lower().startswith("/help") or text == "/start":
                reply = (
                    "🤖 דירה-האנטר — פקודות:\n\n"
                    "/חוף 1.5 — חפש עד 1.5 ק'מ מהחוף\n"
                    "/חוף כבוי — חזור לסריקה לפי שכונות\n"
                    "/מחיר 5000 8000 — שנה טווח מחיר\n"
                    "/חדרים 2 4 — שנה מספר חדרים\n"
                    "/סטטוס — הצג הגדרות נוכחיות\n"
                    "/עזרה — הצג הודעה זו"
                )
            else:
                reply = None

            if reply:
                requests.post(f"{base_url}/sendMessage",
                    json={"chat_id": chat_id, "text": reply},
                    timeout=10)

            save_tg_offset(update_id + 1)

        if changed:
            save_config(config)
            logger.info("Config updated via Telegram command")

    except Exception as e:
        logger.warning(f"Error processing commands: {e}")

    return config


def main():
    logger.info("=" * 50)
    logger.info("🏠 דירה-האנטר — Starting scan")
    logger.info("=" * 50)

    config = load_config()

    telegram_token = get_env_or_fail("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = get_env_or_fail("TELEGRAM_CHAT_ID")

    # בדוק פקודות חדשות מהמשתמש BEFORE the scan
    config = process_telegram_commands(telegram_token, telegram_chat_id, config)

    logger.info(f"City: {config['search']['city']}")
    logger.info(f"Price: ₪{config['search']['min_price']:,} - ₪{config['search']['max_price']:,}")
    logger.info(f"Rooms: {config['search']['min_rooms']} - {config['search']['max_rooms']}")
    beach = config["search"].get("max_distance_from_beach_km", 0)
    if beach:
        logger.info(f"Beach filter: {beach} km")
    else:
        logger.info(f"Neighborhoods: {len(config['search'].get('neighborhoods', []))} areas")

    db = ApartmentDB()
    scraper = Yad2Scraper(config)
    scorer = ApartmentScorer(config)
    notifier = TelegramNotifier(telegram_token, telegram_chat_id, config)

    logger.info("\n📡 Scanning Yad2...")
    apartments = scraper.scrape(max_pages=3)
    logger.info(f"Found {len(apartments)} apartments matching filters")

    pending_apartments = []
    skipped_dup = 0
    for apt in apartments:
        apt.score = scorer.score(apt)
        # בדוק שינוי מחיר לפני שמירה (כדי להשוות למחיר הישן)
        price_change = db.check_price_change(apt.id, apt.price)
        if price_change:
            logger.info(f"  [💰 PRICE] {apt.neighborhood} | ₪{price_change['old_price']:,} → ₪{price_change['new_price']:,} ({price_change['pct']:+.1f}%)")
        if db.is_unsent(apt.id):
            # בדיקה כפולה: אולי דירה זהה כבר נשלחה עם token אחר
            if db.is_duplicate_by_content(apt.neighborhood, apt.address, apt.rooms, apt.price):
                logger.info(f"  [DUP] {apt.rooms}חד | ₪{apt.price:,} | {apt.neighborhood}, {apt.address} — כבר נשלחה בעבר")
                db.mark_notified(apt.id)  # סמן כדי שלא תופיע שוב
                skipped_dup += 1
            else:
                threshold = config.get("scan", {}).get("score_threshold", 0)
                if apt.score >= threshold:
                    pending_apartments.append(apt)
                    status = "NEW" if db.is_new(apt.id) else "PENDING"
                    beach_info = f" | {apt.distance_to_beach_km:.1f}km חוף" if apt.distance_to_beach_km >= 0 else ""
                    logger.info(f"  [{status}] {apt.rooms}חד | ₪{apt.price:,} | {apt.neighborhood}{beach_info} | Score: {apt.score}")
        db.save_apartment(apt)
    if skipped_dup:
        logger.info(f"  ⏭ Skipped {skipped_dup} content-duplicate apartments")

    logger.info(f"\n📊 Results: {len(apartments)} total, {len(pending_apartments)} pending")

    if pending_apartments:
        max_send = config.get("scan", {}).get("max_results_per_scan", 10)
        pending_apartments.sort(key=lambda a: a.score, reverse=True)
        to_send = pending_apartments[:max_send]
        logger.info(f"\n📱 Sending {len(to_send)} Telegram alerts (top {max_send} by score)...")
        sent_count = 0
        for apt in to_send:
            success = notifier.send_apartment_alert(apt)
            # סמן כ-notified תמיד — גם אם שעות שקטות, כדי לא לשלוח שוב
            db.mark_notified(apt.id)
            if success:
                sent_count += 1
            time.sleep(1)
        logger.info(f"✅ Sent {sent_count}/{len(to_send)} alerts")
        if sent_count > 3:
            notifier.send_summary(to_send[:sent_count], len(apartments))

        # סמן את כל השאר (שלא נשלחו בגלל max_send) כ-notified כדי למנוע הצפה
        skipped = pending_apartments[max_send:]
        for apt in skipped:
            db.mark_notified(apt.id)
        if skipped:
            logger.info(f"⏭ Marked {len(skipped)} additional apartments as seen (over max_send limit)")
    else:
        logger.info("😴 No pending apartments this scan")

    # שלח התראות על שינויי מחיר
    price_changes = db.get_unsent_price_changes()
    if price_changes:
        logger.info(f"\n💰 Found {len(price_changes)} price changes to notify")
        for change in price_changes[:5]:  # מקסימום 5 התראות מחיר לסריקה
            success = notifier.send_price_change_alert(change)
            # סמן תמיד כנשלח — גם בשעות שקטות
            db.mark_price_change_notified(change["id"])
            if success:
                logger.info(f"  💰 Price alert sent: {change['apartment_id']}")
            time.sleep(1)

    db.log_scan(source="yad2", total=len(apartments), new=len(pending_apartments))
    stats = db.get_stats()
    logger.info(f"\n📈 DB: Total={stats['total_apartments']} Notified={stats['notified']} Unsent={stats['unsent']}")
    logger.info(f"\n🏁 Scan complete at {datetime.now().strftime('%H:%M:%S')}")


def run_loop():
    """לולאה ראשית — רץ כל X דקות (לפי config)"""
    config = load_config()
    interval = config.get("scan", {}).get("interval_minutes", 10)
    logger.info(f"🔄 דירה-האנטר — מצב לולאה: סריקה כל {interval} דקות")

    # שלח הודעת הפעלה
    try:
        telegram_token = get_env_or_fail("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = get_env_or_fail("TELEGRAM_CHAT_ID")
        notifier = TelegramNotifier(telegram_token, telegram_chat_id, config)
        notifier.send_startup_message()
    except Exception:
        pass

    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"❌ שגיאה בסריקה: {e}")

        # קרא מחדש את ה-interval (אולי המשתמש שינה)
        try:
            config = load_config()
            interval = config.get("scan", {}).get("interval_minutes", 10)
        except Exception:
            pass

        logger.info(f"💤 ממתין {interval} דקות לסריקה הבאה...")
        time.sleep(interval * 60)


if __name__ == "__main__":
    # אם יש ארגומנט "once" — רץ פעם אחת ויוצא
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        main()
    else:
        run_loop()
