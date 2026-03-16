"""
Telegram Bot — שליחת התראות על דירות חדשות
"""

import requests
import logging
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramNotifier:
    """שולח התראות על דירות חדשות ב-Telegram"""

    def __init__(self, bot_token: str, chat_id: str, config: dict):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.config = config.get("telegram", {})
        self.api_url = TELEGRAM_API.format(token=bot_token)

    def _is_quiet_hours(self) -> bool:
        """בודק אם עכשיו שעות שקטות"""
        if not self.config.get("quiet_hours_start"):
            return False

        now = datetime.now()
        try:
            start = datetime.strptime(self.config["quiet_hours_start"], "%H:%M").time()
            end = datetime.strptime(self.config["quiet_hours_end"], "%H:%M").time()

            if start <= end:
                return start <= now.time() <= end
            else:  # Overnight (e.g., 23:00 - 07:00)
                return now.time() >= start or now.time() <= end
        except Exception:
            return False

    def _format_apartment_message(self, apt) -> str:
        """מעצב הודעה יפה על דירה"""
        # Score emoji
        if apt.score >= 85:
            score_emoji = "🟢"
        elif apt.score >= 65:
            score_emoji = "🟡"
        else:
            score_emoji = "🔴"

        # Time ago
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

        # Source badge
        source_badge = "🟠 יד2" if apt.source == "yad2" else "🔵 פייסבוק"

        msg = f"""🏠 *דירה חדשה נמצאה\\!*

{source_badge}

📍 *{self._escape_md(apt.neighborhood)}*, {self._escape_md(apt.address)}
🛏 {apt.rooms} חדרים \\| {apt.area_sqm} מ״ר \\| קומה {apt.floor}
💰 *₪{apt.price:,}* לחודש

📝 {self._escape_md(apt.description[:150])}

⏰ עלתה לפני: {self._escape_md(time_ago)}
{score_emoji} ציון התאמה: *{apt.score}/100*"""

        if apt.contact_name:
            msg += f"\n👤 {self._escape_md(apt.contact_name)}"

        return msg

    def _escape_md(self, text: str) -> str:
        """Escape special characters for Telegram MarkdownV2"""
        if not text:
            return ""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', 
                        '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = str(text).replace(char, f'\\{char}')
        return text

    def _build_keyboard(self, apt) -> dict:
        """בונה כפתורים לפעולות מהירות"""
        buttons = []

        # Open in Yad2 / source
        if apt.url:
            buttons.append([{
                "text": "🔗 פתח מודעה",
                "url": apt.url
            }])

        # Call button (tel: link)
        if apt.contact_phone:
            phone = apt.contact_phone.replace("-", "").replace(" ", "")
            buttons.append([{
                "text": f"📞 חייג עכשיו — {apt.contact_phone}",
                "url": f"tel:{phone}"
            }])

        # WhatsApp button
        if apt.contact_phone:
            phone = apt.contact_phone.replace("-", "").replace(" ", "")
            if not phone.startswith("972"):
                phone = "972" + phone.lstrip("0")
            wa_text = f"היי, ראיתי את המודעה שלך ביד2 לדירה ב{apt.neighborhood}. האם היא עדיין פנויה?"
            buttons.append([{
                "text": "💬 WhatsApp",
                "url": f"https://wa.me/{phone}?text={requests.utils.quote(wa_text)}"
            }])

        return {"inline_keyboard": buttons}

    def send_apartment_alert(self, apt) -> bool:
        """שולח התראה על דירה חדשה"""
        if self._is_quiet_hours():
            logger.info(f"Quiet hours — skipping notification for {apt.id}")
            return False

        message = self._format_apartment_message(apt)
        keyboard = self._build_keyboard(apt)

        try:
            # Send photo if available
            if apt.image_url and self.config.get("send_photos", True):
                response = requests.post(
                    f"{self.api_url}/sendPhoto",
                    json={
                        "chat_id": self.chat_id,
                        "photo": apt.image_url,
                        "caption": message,
                        "parse_mode": "MarkdownV2",
                        "reply_markup": keyboard
                    },
                    timeout=10
                )
                if response.status_code == 200:
                    logger.info(f"✅ Photo alert sent for {apt.id}")
                    return True
                # Fall back to text if photo fails
                logger.warning(f"Photo send failed, falling back to text")

            # Send text message
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "MarkdownV2",
                    "reply_markup": keyboard,
                    "disable_web_page_preview": False
                },
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"✅ Alert sent for {apt.id}")
                return True
            else:
                logger.error(f"Telegram error: {response.status_code} — {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
            return False

    def send_summary(self, apartments: list, total_scanned: int) -> bool:
        """שולח סיכום סריקה"""
        if not apartments:
            return True

        msg = f"""📊 *סיכום סריקה*

🔍 נסרקו: {total_scanned} מודעות
✅ התאמות חדשות: {len(apartments)}
⏰ {self._escape_md(datetime.now().strftime('%H:%M %d/%m/%Y'))}

💰 טווח מחירים: ₪{min(a.price for a in apartments):,} \\- ₪{max(a.price for a in apartments):,}"""

        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": msg,
                    "parse_mode": "MarkdownV2"
                },
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending summary: {e}")
            return False

    def send_startup_message(self) -> bool:
        """שולח הודעה שהמערכת התחילה לעבוד"""
        msg = "🚀 *דירה\\-האנטר הופעל\\!*\n\nהמערכת סורקת דירות\\.\\.\\."
        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": msg,
                    "parse_mode": "MarkdownV2"
                },
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False
