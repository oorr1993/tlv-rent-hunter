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
        """בודק אם הדירה חדשה (לא ראינו אותה לפני כן)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM apartments WHERE id = ?",
                (apartment_id,)
            )
            return cursor.fetchone() is None

    def save_apartment(self, apt) -> bool:
        """שומר דירה למסד הנתונים"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO apartments 
                    (id, source, title, price, rooms, area_sqm, floor,
                     neighborhood, address, description, contact_name,
                     contact_phone, url, image_url, date_added, score, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    apt.id, apt.source, apt.title, apt.price, apt.rooms,
                    apt.area_sqm, apt.floor, apt.neighborhood, apt.address,
                    apt.description, apt.contact_name, apt.contact_phone,
                    apt.url, apt.image_url, apt.date_added, apt.score,
                    json.dumps(apt.raw_data, ensure_ascii=False)
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving apartment {apt.id}: {e}")
            return False

    def mark_notified(self, apartment_id: str):
        """מסמן דירה כ'נשלחה התראה'"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE apartments SET notified = 1 WHERE id = ?",
                (apartment_id,)
            )
            conn.commit()

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
            today = conn.execute(
                "SELECT COUNT(*) FROM apartments WHERE first_seen >= date('now')"
            ).fetchone()[0]

            return {
                "total_apartments": total,
                "notified": notified,
                "found_today": today,
            }
