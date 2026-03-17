"""
Telegram Bot — שליחת התראות על דירות חדשות
"""
import requests
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}"


def get_israel_time():
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year
    last_sunday_march = max(d for d in range(25, 32) if datetime(year, 3, d).weekday() == 6)
    last_sunday_october = max(d for d in range(25, 32) if datetime(year, 10, d).weekday() == 6)
    dst_start = datetime(year, 3, last_sunday_march, 2, 0, tzinfo=timezone.utc)
    dst_end = datetime(year, 10, last_sunday_october, 2, 0, tzinfo=timezone.utc)
    offset = timedelta(hours=3) if dst_start <= now_utc < dst_end else timedelta(hours=2)
    return now_utc + offset


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, config: dict):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.config = config.get("telegram", {})
        self.api_url = TELEGRAM_API.format(token=bot_token)

    def _is_quiet_hours(self) -> bool:
        if not self.config.get("quiet_hours_start"):
            return False
        now = get_israel_time()
        try:
            start = datetime.strptime(self.config["quiet_hours_start"], "%H:%M").time()
            end = datetime.strptime(self.config["quiet_hours_end"], "%H:%M").time()
            t = now.time()
            logger.info(f"IL time: {now.strftime('%H:%M')} | Quiet: {self.config['quiet_hours_start']}-{self.config['quiet_hours_end']}")
            if start <= end:
                return start <= t <= end
            return t >= start or t <= end
        except Exception:
            return False

    def _format_message(self, apt) -> str:
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
                time_ago = f"{int(diff.total_seconds()/60)} דקות"
            elif diff.total_seconds() < 86400:
                time_ago = f"{int(diff.total_seconds()/3600)} שעות"
            else:
                time_ago = f"{diff.days} ימים"
        except Exception:
            time_ago = "?"

        msg_lines = [
            "🏠 דירה חדשה נמצאה!",
            "",
            f"📍 {apt.neighborhood}, {apt.address}",
            f"🛏 {apt.rooms} חדרים | {apt.area_sqm} מ''ר | קומה {apt.floor}",
            f"💰 ₪{apt.price:,} לחודש",
        ]

        # הצג מרחק מהחוף אם זמין
        if hasattr(apt, "distance_to_beach_km") and apt.distance_to_beach_km >= 0:
            msg_lines.append(f"🏖 {apt.distance_to_beach_km:.1f} ק''מ מהחוף")

        msg_lines.append("")

        if apt.description:
            msg_lines.append(f"📝 {apt.description[:200]}")
            msg_lines.append("")

        msg_lines.append(f"⏰ עלתה לפני: {time_ago}")
        msg_lines.append(f"{score_emoji} ציון: {apt.score}/100")

        if apt.contact_name:
            msg_lines.append(f"👤 {apt.contact_name}")
        if apt.url:
            msg_lines.append(f"")
            msg_lines.append(f"🔗 {apt.url}")

        return "\n".join(msg_lines)

    def _build_keyboard(self, apt) -> dict:
        buttons = []
        if apt.url:
            buttons.append([{"text": "🔗 פתח מודעה ביד2", "url": apt.url}])
        if apt.contact_phone:
            phone = apt.contact_phone.replace("-","").replace(" ","")
            buttons.append([{"text": f"📞 {apt.contact_phone}", "url": f"tel:{phone}"}])
            wa_phone = ("972" + phone.lstrip("0")) if not phone.startswith("972") else phone
            wa_text = f"היי, ראיתי את המודעה ביד2 לדירה ב{apt.neighborhood}. האם היא עדיין פנויה?"
            buttons.append([{"text": "💬 WhatsApp", "url": f"https://wa.me/{wa_phone}?text={requests.utils.quote(wa_text)}"}])
        return {"inline_keyboard": buttons}

    def send_apartment_alert(self, apt) -> bool:
        if self._is_quiet_hours():
            logger.info(f"Quiet hours — skipping {apt.id}")
            return False
        message = self._format_message(apt)
        keyboard = self._build_keyboard(apt)
        try:
            # נסה לשלוח עם תמונה מה-CDN של יד2
            if apt.image_url and self.config.get("send_photos", True):
                r = requests.post(
                    f"{self.api_url}/sendPhoto",
                    json={"chat_id": self.chat_id, "photo": apt.image_url, "caption": message, "reply_markup": keyboard},
                    timeout=15
                )
                if r.status_code == 200:
                    logger.info(f"✅ Photo sent for {apt.id}")
                    return True
                logger.warning(f"Photo failed ({r.status_code}): {r.text[:150]}")
            # נסה טקסט
            r = requests.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": message, "reply_markup": keyboard, "disable_web_page_preview": True},
                timeout=15
            )
            if r.status_code == 200:
                logger.info(f"✅ Text sent for {apt.id}")
                return True
            logger.error(f"Telegram error {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"Error: {e}")
            return False

    def send_summary(self, apartments: list, total_scanned: int) -> bool:
        if not apartments: return True
        msg = (
            f"📊 סיכום סריקה\n"
            f"נסרקו: {total_scanned} | נשלחו: {len(apartments)}\n"
            f"₪{min(a.price for a in apartments):,} - ₪{max(a.price for a in apartments):,}"
        )
        try:
            r = requests.post(f"{self.api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": msg}, timeout=10)
            return r.status_code == 200
        except Exception: return False

    def send_startup_message(self) -> bool:
        try:
            r = requests.post(f"{self.api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": "🚀 דירה-האנטר הופעל! שלח /עזרה לרשימת פקודות."}, timeout=10)
            return r.status_code == 200
        except Exception: return False
