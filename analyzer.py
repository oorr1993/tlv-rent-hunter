"""
Apartment Analyzer — ציון התאמה לכל דירה
מדרג דירות לפי קרבה לקריטריונים שהגדרת
"""

import logging

logger = logging.getLogger(__name__)


class ApartmentScorer:
    """מחשב ציון התאמה לכל דירה (0-100)"""

    def __init__(self, config: dict):
        self.search = config["search"]
        self.weights = config.get("scoring", {
            "price_weight": 30,
            "location_weight": 25,
            "size_weight": 20,
            "freshness_weight": 25,
        })

    def score(self, apt) -> int:
        """מחשב ציון כולל לדירה"""
        price_score = self._score_price(apt.price)
        location_score = self._score_location(apt.neighborhood)
        size_score = self._score_size(apt.area_sqm, apt.rooms)
        freshness_score = self._score_freshness(apt.date_added)

        total = (
            price_score * self.weights["price_weight"] / 100 +
            location_score * self.weights["location_weight"] / 100 +
            size_score * self.weights["size_weight"] / 100 +
            freshness_score * self.weights["freshness_weight"] / 100
        )

        return min(100, max(0, int(total)))

    def _score_price(self, price: int) -> int:
        """ציון מחיר — ככל שקרוב יותר לתחתית הטווח, יותר טוב"""
        if price <= 0:
            return 50  # unknown price

        min_p = self.search.get("min_price", 0)
        max_p = self.search.get("max_price", 99999)
        mid = (min_p + max_p) / 2

        if price <= min_p:
            return 100
        elif price >= max_p:
            return 20
        elif price <= mid:
            # Lower half of range = good
            ratio = (price - min_p) / (mid - min_p)
            return int(100 - ratio * 25)
        else:
            # Upper half = less good
            ratio = (price - mid) / (max_p - mid)
            return int(75 - ratio * 55)

    def _score_location(self, neighborhood: str) -> int:
        """ציון מיקום — שכונות מועדפות מקבלות ציון גבוה"""
        preferred = self.search.get("neighborhoods", [])
        if not preferred:
            return 70  # no preference = neutral

        if not neighborhood:
            return 40

        # Exact match
        for pref in preferred:
            if pref in neighborhood or neighborhood in pref:
                # Priority by order in list (first = most preferred)
                idx = preferred.index(pref)
                return max(60, 100 - idx * 5)

        return 30  # Not in preferred neighborhoods

    def _score_size(self, area: int, rooms: float) -> int:
        """ציון גודל — מבוסס על שטח וחדרים"""
        score = 50  # default

        min_area = self.search.get("min_area_sqm", 0)
        if area > 0 and min_area > 0:
            if area >= min_area * 1.3:
                score = 100
            elif area >= min_area:
                ratio = (area - min_area) / (min_area * 0.3)
                score = int(70 + ratio * 30)
            else:
                score = max(20, int(70 * area / min_area))

        # Bonus for ideal room count
        min_rooms = self.search.get("min_rooms", 0)
        max_rooms = self.search.get("max_rooms", 99)
        ideal_rooms = (min_rooms + max_rooms) / 2
        if rooms > 0:
            room_diff = abs(rooms - ideal_rooms)
            room_bonus = max(0, 10 - room_diff * 5)
            score = min(100, score + int(room_bonus))

        return score

    def _score_freshness(self, date_added: str) -> int:
        """ציון טריות — מודעות חדשות מקבלות ציון גבוה"""
        from datetime import datetime

        try:
            added = datetime.fromisoformat(date_added.replace("Z", "+00:00"))
            diff_hours = (datetime.now() - added.replace(tzinfo=None)).total_seconds() / 3600

            if diff_hours < 1:
                return 100
            elif diff_hours < 3:
                return 90
            elif diff_hours < 6:
                return 80
            elif diff_hours < 12:
                return 70
            elif diff_hours < 24:
                return 55
            elif diff_hours < 48:
                return 40
            else:
                return 25
        except Exception:
            return 50  # Unknown date
