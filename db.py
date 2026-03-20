"""
Database — מסד נתונים פשוט למניעת כפילויות
משתמש ב-SQLite (קובץ אחד, אפס תלויות)
"""
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "apartments.db"


class ApartmentDB:
    """מסד נתונים מקומי לאחסון דירות ומניעת כפילויות"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self):
        """יוצר את הטבלאות אם לא קיימות"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS apartments (
                    id TEXT PRIMARY KEY,
                    source TEXT,
                    title TEXT,
                    price INTEGER,
                    rooms REAL,
                    area_sqm INTEGER,
                    floor INTEGER,
                    neighborhood TEXT,
                    address TEXT,
                    description TEXT,
                    contact_name TEXT,
                    contact_phone TEXT,
                    url TEXT,
                    image_url TEXT,
                    date_added TEXT,
                    score INTEGER DEFAULT 0,
                    notified INTEGER DEFAULT 0,
                    favorited INTEGER DEFAULT 0,
                    first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                    raw_data TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    apartment_id TEXT,
                    old_price INTEGER,
                    new_price INTEGER,
                    changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    notified INTEGER DEFAULT 0,
                    FOREIGN KEY (apartment_id) REFERENCES apartments(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_price_history_apartment
                ON price_history (apartment_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_apartments_notified
                ON apartments (notified)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    source TEXT,
                    total_found INTEGER,
                    new_found INTEGER,
                    errors TEXT
                )
            """)
            conn.commit()

    def is_new(self, apartment_id: str) -> bool:
        """בודק אם הדירה חדשה לחלוטין (מעולם לא נראתה)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM apartments WHERE id = ?",
                (apartment_id,)
            )
            return cursor.fetchone() is None

    def is_duplicate_by_content(self, neighborhood: str, address: str, rooms: float, price: int) -> bool:
        """בודק אם דירה דומה כבר נשלחה (אותה שכונה+כתובת+חדרים+מחיר דומה).
        תופס מקרים שבהם מודעה נמחקה ופורסמה מחדש עם token חדש."""
        if not address or not neighborhood:
            return False
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 1 FROM apartments
                    WHERE neighborhood = ? AND address = ? AND rooms = ?
                    AND notified = 1
                    AND ABS(price - ?) < ?
                    LIMIT 1
                """, (neighborhood, address, rooms, price, max(500, price * 0.1)))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking content duplicate: {e}")
            return False

    def is_unsent(self, apartment_id: str) -> bool:
        """בודק אם הדירה עוד לא נשלחה התראה עליה (חדשה לגמרי OR נראתה בשעות שקטות)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT notified FROM apartments WHERE id = ?",
                (apartment_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return True  # Brand new - never seen
            return row[0] == 0  # Seen but not yet notified

    def save_apartment(self, apt) -> bool:
        """שומר דירה למסד הנתונים — בלי לאפס את דגל notified (UPSERT)"""
        try:
            raw = json.dumps(apt.raw_data, ensure_ascii=False)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO apartments
                    (id, source, title, price, rooms, area_sqm, floor,
                     neighborhood, address, description, contact_name,
                     contact_phone, url, image_url, date_added, score, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        price = excluded.price,
                        rooms = excluded.rooms,
                        area_sqm = excluded.area_sqm,
                        floor = excluded.floor,
                        neighborhood = excluded.neighborhood,
                        address = excluded.address,
                        description = excluded.description,
                        contact_name = excluded.contact_name,
                        contact_phone = excluded.contact_phone,
                        url = excluded.url,
                        image_url = excluded.image_url,
                        score = excluded.score,
                        raw_data = excluded.raw_data
                """, (
                    apt.id, apt.source, apt.title, apt.price, apt.rooms,
                    apt.area_sqm, apt.floor, apt.neighborhood, apt.address,
                    apt.description, apt.contact_name, apt.contact_phone,
                    apt.url, apt.image_url, apt.date_added, apt.score, raw
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving apartment {apt.id}: {e}")
            return False

    def check_price_change(self, apartment_id: str, new_price: int) -> dict:
        """בודק אם המחיר השתנה מאז השמירה האחרונה. מחזיר dict עם פרטים או None"""
        if not new_price:
            return None
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT price FROM apartments WHERE id = ? AND notified = 1",
                    (apartment_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    return None  # דירה חדשה או שלא נשלחה — לא רלוונטי
                old_price = row[0]
                if old_price and old_price != new_price:
                    # שמור בהיסטוריה
                    conn.execute("""
                        INSERT INTO price_history (apartment_id, old_price, new_price)
                        VALUES (?, ?, ?)
                    """, (apartment_id, old_price, new_price))
                    conn.commit()
                    diff = new_price - old_price
                    pct = round((diff / old_price) * 100, 1)
                    return {
                        "apartment_id": apartment_id,
                        "old_price": old_price,
                        "new_price": new_price,
                        "diff": diff,
                        "pct": pct,
                    }
        except Exception as e:
            logger.error(f"Error checking price change for {apartment_id}: {e}")
        return None

    def get_unsent_price_changes(self) -> list:
        """מחזיר שינויי מחיר שעוד לא נשלחו"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT ph.id, ph.apartment_id, ph.old_price, ph.new_price, ph.changed_at,
                           a.neighborhood, a.address, a.rooms, a.area_sqm, a.floor, a.url
                    FROM price_history ph
                    JOIN apartments a ON ph.apartment_id = a.id
                    WHERE ph.notified = 0
                    ORDER BY ph.changed_at DESC
                """)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting unsent price changes: {e}")
            return []

    def mark_price_change_notified(self, price_history_id: int):
        """מסמן שינוי מחיר כ'נשלח'"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE price_history SET notified = 1 WHERE id = ?",
                    (price_history_id,)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error marking price change {price_history_id} as notified: {e}")

    def mark_notified(self, apartment_id: str):
        """מסמן דירה כ'נשלחה התראה'"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE apartments SET notified = 1 WHERE id = ?",
                    (apartment_id,)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error marking apartment {apartment_id} as notified: {e}")

    def is_first_run(self) -> bool:
        """בודק אם זו הריצה הראשונה (DB ריק או כמעט ריק)"""
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM apartments").fetchone()[0]
            return count == 0

    def seed_apartments(self, apartments: list) -> int:
        """ריצה ראשונה: שמור את כל הדירות כ-notified בלי לשלוח.
        זה יוצר את 'הבסיס' — בסריקות הבאות רק דירות חדשות יישלחו."""
        count = 0
        for apt in apartments:
            self.save_apartment(apt)
            self.mark_notified(apt.id)
            count += 1
        return count

    def log_scan(self, source: str, total: int, new: int, errors: str = ""):
        """מתעד סריקה"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO scan_log (source, total_found, new_found, errors)
                VALUES (?, ?, ?, ?)
            """, (source, total, new, errors))
            conn.commit()

    def get_stats(self) -> dict:
        """מחזיר סטטיסטיקות"""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM apartments").fetchone()[0]
            notified = conn.execute("SELECT COUNT(*) FROM apartments WHERE notified=1").fetchone()[0]
            unsent = conn.execute("SELECT COUNT(*) FROM apartments WHERE notified=0").fetchone()[0]
            today = conn.execute(
                "SELECT COUNT(*) FROM apartments WHERE first_seen >= date('now')"
            ).fetchone()[0]
        return {
            "total_apartments": total,
            "notified": notified,
            "unsent": unsent,
            "found_today": today,
        }
