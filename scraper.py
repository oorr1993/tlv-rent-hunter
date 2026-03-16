"""
יד2 סורק — Yad2 Rental Apartment Scraper
סורק דירות להשכרה מיד2 דרך ה-API הפנימי שלהם
"""

import requests
import time
import random
import logging
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

# Yad2 internal API endpoints
YAD2_API_BASE = "https://gw.yad2.co.il/feed-search-legacy/realestate/rent"
YAD2_ITEM_URL = "https://www.yad2.co.il/item/{token}"

# Headers to mimic a real browser
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.yad2.co.il",
    "Referer": "https://www.yad2.co.il/realestate/rent",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


@dataclass
class Apartment:
    """מבנה נתונים לדירה"""
    id: str
    source: str  # "yad2" or "facebook"
    title: str
    price: int
    rooms: float
    area_sqm: int
    floor: int
    neighborhood: str
    address: str
    description: str
    contact_name: str
    contact_phone: str
    url: str
    image_url: Optional[str]
    date_added: str
    raw_data: dict
    score: int = 0

    def to_dict(self):
        return asdict(self)


class Yad2Scraper:
    """סורק דירות מיד2"""

    def __init__(self, config: dict):
        self.config = config["search"]
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _build_params(self, page: int = 1) -> dict:
        """בונה את הפרמטרים לקריאת API"""
        params = {
            "city": self.config["city_code"],
            "dealType": "2",  # 2 = rent
            "property": "1",  # 1 = apartment
            "page": page,
        }

        if self.config.get("min_price"):
            params["price"] = f"{self.config['min_price']}-{self.config['max_price']}"

        if self.config.get("min_rooms"):
            params["rooms"] = f"{self.config['min_rooms']}-{self.config['max_rooms']}"

        if self.config.get("has_parking"):
            params["parking"] = "1"

        if self.config.get("has_elevator"):
            params["elevator"] = "1"

        if self.config.get("has_balcony"):
            params["balcony"] = "1"

        if self.config.get("immediate_entry"):
            params["EnterDate"] = "immediate"

        return params

    def _parse_item(self, item: dict) -> Optional[Apartment]:
        """ממיר פריט מ-API לאובייקט Apartment"""
        try:
            # Extract basic info
            token = item.get("token", item.get("id", ""))
            price_str = item.get("price", "0")

            # Handle price formats like "₪5,500" or "5500"
            price = 0
            if isinstance(price_str, str):
                price = int("".join(filter(str.isdigit, price_str)) or "0")
            elif isinstance(price_str, (int, float)):
                price = int(price_str)

            rooms = float(item.get("rooms_text", item.get("Rooms_text", "0"))
                         .replace("חדרים", "").replace("חדר", "").strip() or "0")
            if rooms == 0:
                rooms = float(item.get("row_4", [{}])[0].get("value", "0")
                             if isinstance(item.get("row_4"), list) and item.get("row_4")
                             else "0")

            area = int(item.get("square_meters", item.get("SquareMeter", 0)) or 0)
            floor = int(item.get("floor", item.get("Floor", 0)) or 0)

            neighborhood = item.get("neighborhood", item.get("neighborhood_text",
                          item.get("Neighborhood_text", "")))
            address = item.get("address_more", item.get("street",
                     item.get("AddressMore", {}).get("text", "")))
            if isinstance(address, dict):
                address = address.get("text", "")

            city = item.get("city_text", item.get("City_text", "תל אביב"))
            description = item.get("info_text", item.get("Ad_highlight_text",
                         item.get("merchant_name", "")))

            contact_name = item.get("contact_name", item.get("ContactName", ""))
            contact_phone = item.get("phone", item.get("PhoneNumber",
                           item.get("merchant_phone", "")))

            # Handle phone - might be hidden
            if isinstance(contact_phone, dict):
                contact_phone = contact_phone.get("title", "")

            # Image
            images = item.get("images", item.get("Images", []))
            image_url = None
            if images and isinstance(images, list):
                first_img = images[0]
                if isinstance(first_img, dict):
                    image_url = first_img.get("src", first_img.get("url", ""))
                elif isinstance(first_img, str):
                    image_url = first_img

            # Date
            date_added = item.get("date", item.get("DateAdded",
                        item.get("date_added", datetime.now().isoformat())))

            # Build title
            title = f"{rooms} חד׳ ב{neighborhood}" if neighborhood else f"{rooms} חד׳ ב{city}"

            url = YAD2_ITEM_URL.format(token=token)

            return Apartment(
                id=f"yad2_{token}",
                source="yad2",
                title=title,
                price=price,
                rooms=rooms,
                area_sqm=area,
                floor=floor,
                neighborhood=neighborhood,
                address=address,
                description=description,
                contact_name=contact_name,
                contact_phone=contact_phone,
                url=url,
                image_url=image_url,
                date_added=date_added,
                raw_data=item,
            )

        except Exception as e:
            logger.error(f"Error parsing Yad2 item: {e}")
            logger.debug(f"Raw item: {item}")
            return None

    def _filter_apartment(self, apt: Apartment) -> bool:
        """בודק אם דירה עומדת בקריטריונים"""
        config = self.config

        # Price filter
        if apt.price > 0:
            if apt.price < config.get("min_price", 0):
                return False
            if apt.price > config.get("max_price", 999999):
                return False

        # Rooms filter
        if apt.rooms > 0:
            if apt.rooms < config.get("min_rooms", 0):
                return False
            if apt.rooms > config.get("max_rooms", 99):
                return False

        # Area filter
        if apt.area_sqm > 0 and config.get("min_area_sqm"):
            if apt.area_sqm < config["min_area_sqm"]:
                return False

        # Floor filter
        if apt.floor > 0 and config.get("max_floor"):
            if apt.floor > config["max_floor"]:
                return False

        # Neighborhood filter
        neighborhoods = config.get("neighborhoods", [])
        if neighborhoods and apt.neighborhood:
            if not any(n in apt.neighborhood for n in neighborhoods):
                return False

        # Keyword exclude filter
        exclude = config.get("keywords_exclude", [])
        full_text = f"{apt.title} {apt.description}".lower()
        for kw in exclude:
            if kw.lower() in full_text:
                return False

        return True

    def scrape(self, max_pages: int = 3) -> list[Apartment]:
        """סורק דירות מיד2"""
        all_apartments = []

        for page in range(1, max_pages + 1):
            try:
                params = self._build_params(page)
                logger.info(f"Fetching Yad2 page {page}...")

                response = self.session.get(
                    YAD2_API_BASE,
                    params=params,
                    timeout=15
                )
                response.raise_for_status()

                data = response.json()

                # Extract items from response
                feed = data.get("data", {}).get("feed", {})
                items = feed.get("feed_items", [])

                if not items:
                    # Try alternative response structure
                    items = data.get("data", {}).get("feed_items",
                           data.get("feed_items", []))

                if not items:
                    logger.info(f"No items found on page {page}")
                    break

                for item in items:
                    # Skip ads and promoted items
                    item_type = item.get("type", "")
                    if item_type in ("ad", "banner", "platinum", "yellow"):
                        continue

                    apt = self._parse_item(item)
                    if apt and self._filter_apartment(apt):
                        all_apartments.append(apt)

                logger.info(f"Page {page}: found {len(items)} items, "
                          f"{len(all_apartments)} match filters so far")

                # Random delay between pages
                if page < max_pages:
                    delay = random.uniform(2.0, 5.0)
                    time.sleep(delay)

            except requests.RequestException as e:
                logger.error(f"Error fetching Yad2 page {page}: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error on page {page}: {e}")
                break

        logger.info(f"Total apartments found: {len(all_apartments)}")
        return all_apartments

    def get_item_details(self, token: str) -> Optional[dict]:
        """מושך פרטים מלאים של מודעה ספציפית (כולל טלפון)"""
        try:
            url = f"https://gw.yad2.co.il/feed-search-legacy/item/{token}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting item details for {token}: {e}")
            return None
