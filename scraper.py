"""
יד2 סורק — Yad2 Rental Apartment Scraper
סורק דירות להשכרה מיד2 דרך סריקת HTML
"""
import requests
import time
import random
import logging
import json
import re
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

YAD2_SEARCH_URL = "https://www.yad2.co.il/realestate/rent"
YAD2_ITEM_URL = "https://www.yad2.co.il/item/{token}"

DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.yad2.co.il/",
}


@dataclass
class Apartment:
        """מבנה נתונים לדירה"""
        id: str
        source: str
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
        """סורק דירות מיד2 דרך HTML"""

    def __init__(self, config: dict):
                self.config = config["search"]
                self.session = requests.Session()
                self.session.headers.update(DEFAULT_HEADERS)

    def _build_params(self, page: int = 1) -> dict:
                """בונה פרמטרי חיפוש"""
                params = {
                    "city": self.config.get("city_code", "5000"),
                    "minRooms": self.config.get("min_rooms", 2),
                    "maxRooms": self.config.get("max_rooms", 4),
                    "priceMin": self.config.get("min_price", 3000),
                    "priceMax": self.config.get("max_price", 7000),
                    "page": page,
                }
                return params

    def _extract_next_data(self, html: str) -> Optional[dict]:
                """מחלץ נתונים מ-__NEXT_DATA__ של Next.js"""
                try:
                                soup = BeautifulSoup(html, "html.parser")
                                script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
                                if script_tag and script_tag.string:
                                                    return json.loads(script_tag.string)
                except Exception as e:
                                logger.error(f"Error extracting __NEXT_DATA__: {e}")
                            return None

    def _parse_item(self, item: dict) -> Optional["Apartment"]:
                """ממיר פריט לאובייקט Apartment"""
        try:
                        token = str(item.get("token", item.get("id", item.get("orderId", ""))))
                        if not token:
                                            return None

                        # Price
                        price_raw = item.get("price", item.get("Price", 0))
                        if isinstance(price_raw, str):
                                            price = int("".join(filter(str.isdigit, price_raw)) or "0")
        else:
                price = int(price_raw or 0)

            # Rooms
            rooms_raw = str(item.get("rooms", item.get("Rooms", item.get("roomsText", "0"))))
            rooms_raw = rooms_raw.replace("חדרים", "").replace("חדר", "").strip()
            try:
                                rooms = float(rooms_raw or 0)
except ValueError:
                rooms = 0.0

            # Area
            area = int(item.get("squareMeter", item.get("squareMeters", item.get("SquareMeter", 0))) or 0)

            # Floor
            floor = int(item.get("floor", item.get("Floor", 0)) or 0)

            # Location
            neighborhood = item.get("neighborhood", item.get("neighborhoodHe", ""))
            if isinstance(neighborhood, dict):
                                neighborhood = neighborhood.get("text", "")
                            address = item.get("street", item.get("address", item.get("streetHe", "")))
            if isinstance(address, dict):
                                address = address.get("text", "")
                            city = item.get("cityHe", item.get("city_text", "תל אביב"))

            # Description
            description = item.get("infoText", item.get("info_text", item.get("merchantName", "")))

            # Contact
            contact_name = item.get("contactName", item.get("contact_name", ""))
            contact_phone = item.get("phone", item.get("contactPhone", ""))
            if isinstance(contact_phone, dict):
                                contact_phone = contact_phone.get("title", "")

            # Image
            images = item.get("images", item.get("Images", []))
            image_url = None
            if images and isinstance(images, list):
                                first = images[0]
                                if isinstance(first, dict):
                                                        image_url = first.get("src", first.get("url", ""))
            elif isinstance(first, str):
                    image_url = first

            # Date
            date_added = item.get("date", item.get("dateAdded", datetime.now().isoformat()))

            # Title
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
            logger.error(f"Error parsing item: {e}")
            return None

    def _filter_apartment(self, apt: "Apartment") -> bool:
                """בודק אם דירה עומדת בקריטריונים"""
        config = self.config

        if apt.price > 0:
                        if apt.price < config.get("min_price", 0):
                                            return False
                                        if apt.price > config.get("max_price", 999999):
                                                            return False

        if apt.rooms > 0:
                        if apt.rooms < config.get("min_rooms", 0):
                                            return False
                                        if apt.rooms > config.get("max_rooms", 99):
                                                            return False

        if apt.area_sqm > 0 and config.get("min_area_sqm"):
                        if apt.area_sqm < config["min_area_sqm"]:
                                            return False

        neighborhoods = config.get("neighborhoods", [])
        if neighborhoods and apt.neighborhood:
                        if not any(n in apt.neighborhood for n in neighborhoods):
                                            return False

        exclude = config.get("keywords_exclude", [])
        full_text = f"{apt.title} {apt.description}".lower()
        for kw in exclude:
                        if kw.lower() in full_text:
                                            return False

        return True

    def scrape(self, max_pages: int = 3) -> list:
                """סורק דירות מיד2 דרך HTML"""
        all_apartments = []

        for page in range(1, max_pages + 1):
                        try:
                                            params = self._build_params(page)
                                            logger.info(f"Fetching Yad2 page {page}...")

                response = self.session.get(
                                        YAD2_SEARCH_URL,
                                        params=params,
                                        timeout=20
                )
                response.raise_for_status()

                # Extract data from Next.js __NEXT_DATA__
                next_data = self._extract_next_data(response.text)

                items = []
                if next_data:
                                        try:
                                                                    # Navigate the Next.js data structure
                                                                    props = next_data.get("props", {})
                                                                    page_props = props.get("pageProps", {})

                                            # Try multiple paths where listings might be
                                                                    feed = (
                                                                        page_props.get("feed") or
                                                                        page_props.get("dehydratedState", {}).get("queries", [{}])[0]
                                                                        .get("state", {}).get("data", {}).get("feed") or
                                                                        {}
                                                                    )

                                            items = (
                                                feed.get("feed_items") or
                                                                            feed.get("feedItems") or
                                                                            feed.get("items") or
                                                                            page_props.get("feedItems") or
                                                                            []
                                            )
except Exception as e:
                        logger.error(f"Error navigating Next.js data: {e}")

                if not items:
                                        # Fallback: try regex to find listing data
                                        logger.info("Trying regex fallback to find listings...")
                    matches = re.findall(
                                                r'"token"\s*:\s*"([^"]+)".*?"price"\s*:\s*(\d+)',
                                                response.text
                    )
                    logger.info(f"Regex found {len(matches)} token/price pairs")
                    if not matches:
                                                logger.info(f"No items found on page {page}, stopping")
                                                break

                logger.info(f"Page {page}: found {len(items)} items")

                for item in items:
                                        item_type = item.get("type", "")
                    if item_type in ("ad", "banner", "platinum", "yellow", "commercial"):
                                                continue

                    apt = self._parse_item(item)
                    if apt and self._filter_apartment(apt):
                                                all_apartments.append(apt)

                if page < max_pages:
                                        delay = random.uniform(3.0, 6.0)
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
                """מושך פרטים מלאים של מודעה"""
        try:
                        url = YAD2_ITEM_URL.format(token=token)
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            next_data = self._extract_next_data(response.text)
            if next_data:
                                return next_data.get("props", {}).get("pageProps", {})
except Exception as e:
            logger.error(f"Error getting item details for {token}: {e}")
        return None
