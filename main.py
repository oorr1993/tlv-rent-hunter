"""
🏠 דירה-האנטר — Main Script
מריץ סריקה, מנתח, ושולח התראות
"""

import json
import os
import sys
import logging
from pathlib import Path
from datetime import datetime

from scraper import Yad2Scraper
from analyzer import ApartmentScorer
from telegram_bot import TelegramNotifier
from db import ApartmentDB

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("apartment-hunter")


def load_config() -> dict:
    """טוען את קובץ ההגדרות"""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_env_or_fail(key: str) -> str:
    """מושך משתנה סביבה או עוצר"""
    value = os.environ.get(key)
    if not value:
        logger.error(f"Missing environment variable: {key}")
        logger.error(f"Set it with: export {key}=your_value")
        sys.exit(1)
    return value


def main():
    """הלופ הראשי"""
    logger.info("=" * 50)
    logger.info("🏠 דירה-האנטר — Starting scan")
    logger.info("=" * 50)

    # Load config
    config = load_config()
    logger.info(f"Config loaded: searching in {config['search']['city']}")
    logger.info(f"Price range: ₪{config['search']['min_price']:,} - ₪{config['search']['max_price']:,}")
    logger.info(f"Rooms: {config['search']['min_rooms']} - {config['search']['max_rooms']}")

    # Initialize components
    telegram_token = get_env_or_fail("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = get_env_or_fail("TELEGRAM_CHAT_ID")

    db = ApartmentDB()
    scraper = Yad2Scraper(config)
    scorer = ApartmentScorer(config)
    notifier = TelegramNotifier(telegram_token, telegram_chat_id, config)

    # === SCRAPE YAD2 ===
    logger.info("\n📡 Scanning Yad2...")
    apartments = scraper.scrape(max_pages=3)
    logger.info(f"Found {len(apartments)} apartments matching filters")

    # === SCORE & FILTER NEW ===
    new_apartments = []
    for apt in apartments:
        # Calculate score
        apt.score = scorer.score(apt)

        # Check if new
        if db.is_new(apt.id):
            # Check score threshold
            threshold = config.get("scan", {}).get("score_threshold", 0)
            if apt.score >= threshold:
                new_apartments.append(apt)
                logger.info(f"  ✨ NEW: {apt.title} | ₪{apt.price:,} | "
                          f"Score: {apt.score}")

        # Save to DB (even if not new, update data)
        db.save_apartment(apt)

    logger.info(f"\n📊 Results: {len(apartments)} total, {len(new_apartments)} new")

    # === SEND NOTIFICATIONS ===
    if new_apartments:
        logger.info(f"\n📱 Sending {len(new_apartments)} Telegram alerts...")

        # Sort by score (best first)
        new_apartments.sort(key=lambda a: a.score, reverse=True)

        sent_count = 0
        for apt in new_apartments:
            success = notifier.send_apartment_alert(apt)
            if success:
                db.mark_notified(apt.id)
                sent_count += 1

            # Small delay between messages
            import time
            time.sleep(1)

        logger.info(f"✅ Sent {sent_count}/{len(new_apartments)} alerts")

        # Send summary if more than 3 new apartments
        if len(new_apartments) > 3:
            notifier.send_summary(new_apartments, len(apartments))
    else:
        logger.info("😴 No new apartments found this scan")

    # === LOG SCAN ===
    db.log_scan(
        source="yad2",
        total=len(apartments),
        new=len(new_apartments)
    )

    # Print stats
    stats = db.get_stats()
    logger.info(f"\n📈 Database stats:")
    logger.info(f"  Total apartments: {stats['total_apartments']}")
    logger.info(f"  Found today: {stats['found_today']}")
    logger.info(f"  Notified: {stats['notified']}")
    logger.info(f"\n🏁 Scan complete at {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
