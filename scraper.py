"""
yad2 scraper - Yad2 Rental Apartment Scraper
Uses the Yad2 map API endpoint
"""
import requests
import logging
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

YAD2_MAP_API = "https://gw.yad2.co.il/realestate-feed/rent/map"
YAD2_ITEM_URL = "https://www.yad2.co.il/item/{token}"

# Tel Aviv full bounding box (lat_min,lon_min,lat_max,lon_max)
TEL_AVIV_BBOX = "32.029253,34.734553,32.146082,34.860195"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.yad2.co.il",
    "Referer": "https://www.yad2.co.il/realestate/rent/tel-aviv-area",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


@dataclass
class Apartment:
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

    def __init__(self, config: dict):
        self.config = config["search"]
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _parse_marker(self, item: dict) -> Optional["Apartment"]:
        try:
            token = str(item.get("token", ""))
            if not token:
                return None

            price = int(item.get("price", 0) or 0)

            details = item.get("additionalDetails", {})
            rooms = float(details.get("roomsCount", 0) or 0)
            area = int(details.get("squareMeter", 0) or 0)

            addr = item.get("address", {})
            floor = int(addr.get("house", {}).get("floor", 0) or 0)
            neighborhood = addr.get("neighborhood", {}).get("text", "")
            street = addr.get("street", {}).get("text", "")
            house_num = addr.get("house", {}).get("number", "")
            city = addr.get("city", {}).get("text", "תל אביב יפו")
            address = f"{street} {house_num}".strip() if street else city

            description = str(item.get("metaData", {}).get("description", ""))
            contact_name = str(item.get("contactInfo", {}).get("contactName", ""))
            contact_phone = str(item.get("contactInfo", {}).get("phone1", {}).get("phoneNumber", ""))

            images = item.get("images", [])
            image_url = None
            if images and isinstance(images, list):
                img = images[0]
                if isinstance(img, dict):
                    image_url = img.get("src", img.get("url", ""))
                elif isinstance(img, str):
                    image_url = img

            date_added = str(item.get("date", datetime.now().isoformat()))
            title = f"{rooms} חד' ב{neighborhood}" if neighborhood else f"{rooms} חד' ב{city}"
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
            if not any(n.strip() in apt.neighborhood for n in neighborhoods):
                return False

        exclude = config.get("keywords_exclude", [])
        full_text = f"{apt.title} {apt.description}".lower()
        for kw in exclude:
            if kw.lower() in full_text:
                return False

        return True

    def scrape(self, max_pages: int = 3) -> list:
        all_apartments = []

        # Build URL manually - bBox commas must NOT be percent-encoded
        url = (
            f"{YAD2_MAP_API}"
            f"?city=5000&area=1&region=3"
            f"&minRooms={self.config.get('min_rooms', 2)}"
            f"&maxRooms={self.config.get('max_rooms', 4)}"
            f"&zoom=11"
            f"&bBox={TEL_AVIV_BBOX}"
        )
        logger.info(f"Fetching Yad2 map API...")

        try:
            response = self.session.get(url, timeout=20)
            logger.info(f"Response status: {response.status_code}")
            response.raise_for_status()

            data = response.json()
            markers = data.get("data", {}).get("markers", [])
            yad1_markers = data.get("data", {}).get("yad1Markers", [])
            all_markers = markers + yad1_markers

            logger.info(f"API returned {len(all_markers)} listings")

            for item in all_markers:
                apt = self._parse_marker(item)
                if apt and self._filter_apartment(apt):
                    all_apartments.append(apt)

            logger.info(f"After price/room/neighborhood filter: {len(all_apartments)} apartments")

        except requests.RequestException as e:
            logger.error(f"Error fetching Yad2 API: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        logger.info(f"Total apartments found: {len(all_apartments)}")
        return all_apartments

    def get_item_details(self, token: str) -> Optional[dict]:
        return None
