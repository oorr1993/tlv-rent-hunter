"""
×××¨×-××× ××¨ â Main Script
×ª××× ××¤×§××××ª ××××¨× ××©×× ×× ×¤××××¨×× ×××× ×××ª
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
    ×§××¨× ××××¢××ª ×××©××ª ××××× ×××¢××× config ×××ª××.
    ×¤×§××××ª × ×ª××××ª:
      /×××£ 1.5    - ×××¨××ª ×¢× 1.5 ×§'× ×××××£
      /×××£ ××××   - ××× ×¤××××¨ ×××£ (××××¨ ××©××× ××ª)
      /××××¨ 5000 8000  - ×©× × ×××× ××××¨
      /×××¨×× 2 4  - ×©× × ×××× ×××¨××
      /×¡××××¡      - ×©×× ×¡××××¡ × ××××
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

            if text.startswith("/×××£") or text.lower().startswith("/beach"):
                parts = text.split()
                if len(parts) >= 2:
                    arg = parts[1].replace(",", ".").strip()
                    if arg in ["××××", "off", "0", "no"]:
                        config["search"]["max_distance_from_beach_km"] = 0
                        reply = "â ×¤××××¨ ×××£ ×××× - ××××¨ ××¡×¨××§× ××¤× ×©××× ××ª"
                    else:
                        try:
                            km = float(arg)
                            config["search"]["max_distance_from_beach_km"] = km
                            reply = f"â ×××¤×© ×××¨××ª ×¢× {km} ×§'× ×××××£"
                        except ValueError:
                            reply = "â ×©××××: /×××£ 1.5 (××¡×¤×¨ ××§'×)"
                else:
                    reply = "ð ×©××××©: /×××£ 1.5 (××¨××§ ××§'× ×××××£)\n/×××£ ×××× ××××××"
                changed = True

            elif text.startswith("/××××¨") or text.lower().startswith("/price"):
                parts = text.split()
                if len(parts) >= 3:
                    try:
                        mn = int(parts[1])
                        mx = int(parts[2])
                        config["search"]["min_price"] = mn
                        config["search"]["max_price"] = mx
                        reply = f"â ××××¨ ×¢××××: âª{mn:,} - âª{mx:,}"
                        changed = True
                    except ValueError:
                        reply = "â ×©××××: /××××¨ 5000 8000"
                else:
                    reply = "ð ×©××××©: /××××¨ 5000 8000"

            elif text.startswith("/×××¨××") or text.lower().startswith("/rooms"):
                parts = text.split()
                if len(parts) >= 3:
                    try:
                        mn = float(parts[1])
                        mx = float(parts[2])
                        config["search"]["min_rooms"] = mn
                        config["search"]["max_rooms"] = mx
                        reply = f"â ×××¨×× ×¢××××: {mn} - {mx}"
                        changed = True
                    except ValueError:
                        reply = "â ×©××××: /×××¨×× 2 4"
                else:
                    reply = "ð ×©××××©: /×××¨×× 2 4"

            elif text.startswith("/×¡××××¡") or text.lower().startswith("/status"):
                s = config["search"]
                beach = s.get("max_distance_from_beach_km", 0)
                beach_txt = f"{beach} ×§'× ×××××£" if beach else "××¤× ×©××× ××ª"
                reply = (
                    f"ð ×¡××××¡ × ××××:\n"
                    f"ð° ××××¨: âª{s['min_price']:,} - âª{s['max_price']:,}\n"
                    f"ð ×××¨××: {s['min_rooms']} - {s['max_rooms']}\n"
                    f"ð ××××¨: {beach_txt}"
                )

            elif text.startswith("/×¢××¨×") or text.lower().startswith("/help") or text == "/start":
                reply = (
                    "ð¤ ×××¨×-××× ××¨ â ×¤×§××××ª:\n\n"
                    "/×××£ 1.5 â ××¤×© ×¢× 1.5 ×§'× ×××××£\n"
                    "/×××£ ×××× â ××××¨ ××¡×¨××§× ××¤× ×©××× ××ª\n"
                    "/××××¨ 5000 8000 â ×©× × ×××× ××××¨\n"
                    "/×××¨×× 2 4 â ×©× × ××¡×¤×¨ ×××¨××\n"
                    "/×¡××××¡ â ××¦× ××××¨××ª × ××××××ª\n"
                    "/×¢××¨× â ××¦× ××××¢× ××"
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
    logger.info("ð  ×××¨×-××× ××¨ â Starting scan")
    logger.info("=" * 50)

    config = load_config()

    telegram_token = get_env_or_fail("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = get_env_or_fail("TELEGRAM_CHAT_ID")

    # ××××§ ×¤×§××××ª ×××©××ª ××××× ×××¢××× config ×××ª××.
    config = process_telegram_commands(telegram_token, telegram_chat_id, config)

    logger.info(f"City: {config['search']['city']}")
    logger.info(f"Price: âª{config['search']['min_price']:,} - âª{config['search']['max_price']:,}")
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

    logger.info("\nð¡ Scanning Yad2...")
    apartments = scraper.scrape(max_pages=3)
    logger.info(f"Found {len(apartments)} apartments matching filters")

    pending_apartments = []
    for apt in apartments:
        apt.score = scorer.score(apt)
        if db.is_unsent(apt.id):
            threshold = config.get("scan", {}).get("score_threshold", 0)
            if apt.score >= threshold:
                pending_apartments.append(apt)
                status = "NEW" if db.is_new(apt.id) else "PENDING"
                beach_info = f" | {apt.distance_to_beach_km:.1f}km ×××£" if apt.distance_to_beach_km >= 0 else ""
                logger.info(f"  [{status}] {apt.rooms}×× | âª{apt.price:,} | {apt.neighborhood}{beach_info} | Score: {apt.score}")
        db.save_apartment(apt)

    logger.info(f"\nð Results: {len(apartments)} total, {len(pending_apartments)} pending")

    if pending_apartments:
        max_send = config.get("scan", {}).get("max_results_per_scan", 50)
        pending_apartments.sort(key=lambda a: a.score, reverse=True)
        to_send = pending_apartments[:max_send]
        logger.info(f"\nð± Sending {len(to_send)} Telegram alerts (top {max_send} by score)...")
        sent_count = 0
        for apt in to_send:
            success = notifier.send_apartment_alert(apt)
            if success:
                db.mark_notified(apt.id)
                sent_count += 1
            time.sleep(1)
        logger.info(f"â Sent {sent_count}/{len(to_send)} alerts")
        if sent_count > 3:
            notifier.send_summary(to_send[:sent_count], len(apartments))
    else:
        logger.info("ð´ No pending apartments this scan")

    db.log_scan(source="yad2", total=len(apartments), new=len(pending_apartments))
    stats = db.get_stats()
    logger.info(f"\nð DB: Total={stats['total_apartments']} Notified={stats['notified']} Unsent={stats['unsent']}")
    logger.info(f"\nð Scan complete at {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
