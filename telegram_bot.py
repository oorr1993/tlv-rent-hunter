"""
Telegram Bot — שליחת התראות על דירות חדשות
"""
import requests
import logging
import json
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def get_israel_time():
    """מחזיר את השעה הנוכחית בישראל (UTC+2 או UTC+3 בקיץ)"""
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year
    import calendar
    last_sunday_march = max(
        day for day in range(25, 32)
        if datetime(year, 3, day).weekday() == 6
    )
    last_sunday_october = max(
        day for day in range(25, 32)
        if datetime(year, 10, day).weekday() == 6
    )
    dst_start = datetime(year, 3, last_sunday_march, 2, 0, tzinfo=timezone.utc)
    dst_end = datetime(year, 10, last_sunday_october, 2, 0, tzinfo=timezone.utc)
    if dst_start <= now_utc < dst_end:
        offset = timedelta(hours=3)
    else:
        offset = timedelta(hours=2)
    return now_utc + offset


class TelegramNotifier:
    """שולח התראות על דירות חדשות ב-Telegram"""

    def __init__(self, bot_token: str, chat_id: str, config: dict):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.config = config.get("telegram", {})
        self.api_url = TELEGRAM_API.format(token=bot_token)

    def _is_quiet_hours(self) -> bool:
        """בודק אם עכשיו שעות שקטות (לפי שעון ישראל)"""
        if not self.config.get("quiet_hours_start"):
            return False
        now = get_israel_time()
        try:
            start = datetime.strptime(self.config["quiet_hours_start"], "%H:%M").time()
            end = datetime.strptime(self.config["quiet_hours_end"], "%H:%M").time()
            current_time = now.time()
            logger.info(f"Israel time: {now.strftime('%H:%M')} | Quiet: {self.config['quiet_hours_start']} - {self.config['quiet_hours_end']}")
            if start <= end:
                return start <= current_time <= end
            else:
                return current_time >= start or current_time <= end
        except Exception:
            return False

    def _format_apartment_message(self, apt) -> str:
        """מעצב הודעה יפה על דירה"""
        if apt.score >= 85:
            score_emoji = "🟢"
        elif apt.score >= 65:
            score_emoji = "🟡"
        else:
            score_emoji = "🔴"
        try:
            added = datetime.fromisoformat(apt.date_added.replace("Z", "+00:00"))
            diff = datetime.now() - added.replace(tzinfo=None)
            if diff.total_seconds() < 3600:
                time_ago = f"{int(diff.total_seconds() / 60)} דקות"
            elif diff.total_seconds() < 86400:
                time_ago = f"{int(diff.total_seconds() / 3600)} שעות"
            else:
                time_ago = f"{diff.days} ימים"
        except Exception:
            time_ago = "לא ידוע"
        source_badge = "🟠 יד2" if apt.source == "yad2" else "🔵 פייסבוק"
        msg = (
            f"🏠 *דירה חדשה נמצאה\\!* {source_badge}\n\n"
            f"📍 *{self._escape_md(apt.neighborhood)}*, {self._escape_md(apt.address)}\n"
            f"🛏 {apt.rooms} חדרים \\| {apt.area_sqm} מ''ר \\| קומה {apt.floor}\n"
            f"💰 *₪{apt.price:,}* לחודש\n"
            f"📝 {self._escape_md(apt.description[:150])}\n"
            f"⏰ עלתה לפני: {self._escape_md(time_ago)}\n"
            f"{score_emoji} ציון התאמה: *{apt.score}/100*"
        )
        if apt.contact_name:
            msg += f"\n👤 {self._escape_md(apt.contact_name)}"
        return msg

    def _escape_md(self, text: str) -> str:
        """Escape special characters for Telegram MarkdownV2"""
        if not text:
            return ""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = str(text).replace(char, f"\\{char}")
        return text

    def _build_keyboard(self, apt) -> dict:
        """בונה כפתורים לפעולות מהירות"""
        buttons = []
        if apt.url:
            buttons.append([{"text": "🔗 פתח מודעה", "url": apt.url}])
        if apt.contact_phone:
            phone = apt.contact_phone.replace("-", "").replace(" ", "")
            buttons.append([{"text": f"📞 חייג — {apt.contact_phone}", "url": f"tel:{phone}"}])
            if not phone.startswith("972"):
                phone = "972" + phone.lstrip("0")
            wa_text = f"היי, ראיתי את המודעה שלך ביד2 לדירה ב{apt.neighborhood}. האם היא עדיין פנויה?"
            buttons.append([{"text": "💬 WhatsApp", "url": f"https://wa.me/{phone}?text={requests.utils.quote(wa_text)}"}])
        return {"inline_keyboard": buttons}

    def send_apartment_alert(self, apt) -> bool:
        """שולח התראה על דירה חדשה"""
        if self._is_quiet_hours():
            logger.info(f"Quiet hours — skipping notification for {apt.id}")
            return False
        message = self._format_apartment_message(apt)
        keyboard = self._build_keyboard(apt)
        try:
            if apt.image_url and self.config.get("send_photos", True):
                response = requests.post(
                    f"{self.api_url}/sendPhoto",
                    json={"chat_id": self.chat_id, "photo": apt.image_url, "caption": message, "parse_mode": "MarkdownV2", "reply_markup": keyboard},
                    timeout=10
                )
                if response.status_code == 200:
                    logger.info(f"✅ Photo alert sent for {apt.id}")
                    return True
                logger.warning(f"Photo failed ({response.status_code}), trying text")
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": message, "parse_mode": "MarkdownV2", "reply_markup": keyboard},
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"✅ Alert sent for {apt.id}")
                return True
            else:
                logger.error(f"Telegram error: {response.status_code} — {response.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
            return False

    def send_summary(self, apartments: list, total_scanned: int) -> bool:
        """שולח סיכום סריקה"""
        if not apartments:
            return True
        msg = (
            f"📊 *סיכום סריקה*\n\n"
            f"🔍 נסרקו: {total_scanned} מודעות\n"
            f"✅ התאמות: {len(apartments)}\n"
            f"💰 ₪{min(a.price for a in apartments):,} \\- ₪{max(a.price for a in apartments):,}"
        )
        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": msg, "parse_mode": "MarkdownV2"},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending summary: {e}")
            return False

    def send_startup_message(self) -> bool:
        """שולח הודעה שהמערכת התחילה לעבוד"""
        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": "🚀 דירה-האנטר הופעל! המערכת סורקת דירות..."},
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False
