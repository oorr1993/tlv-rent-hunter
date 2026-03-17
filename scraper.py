פילטרמרחקחמדהבחוףחדבפילטרשכונותאםאיןפילטרחוףבודקיםשכונותפילטרטריות—רקמודעותמשעותאחרונותexx_caegpet_ hEoxucresp t=i ocno nafsi ge.:g
e t ( " m a x _ l i s t ilnogg_gaegre._ehroruorrs("f," E4r8r)o
r   p a r s i n gi fi tmeamx:_ a{gee}_"h)o
u r s   >   0   a n d   arpett.udrant eN_oanded
e
d : 
    d e f   _ f i l t e rt_rayp:a
    r t m e n t ( s e l f ,   a p t :a d"dAepda r=t mdeantte"t)i m-e>. fbrooomli:s
    o f o r m a t ( acpotn.fdiagt e=_ asdedlefd..croenpfliagc
    e
    ( " Z " ,   " + 0i0f: 0a0p"t).)p
    r i c e   >   0 : 
                  a d d e d _infa iavpet .=p raidcdee d<. rceopnlfaicge.(gtezti(n"fmoi=nN_opnrei)c
                  e " ,   0 ) :   r e t u r n   F aalgsee 
                  =   d a t e t i m e . n oiwf( )a p-t .apdrdiecde_ n>a icvoen
                  f i g . g e t ( " m a x _ p r i cief" ,a g9e9 9>9 9t9i)m:e dreelttuar(nh oFuarlss=em
                  a x _ a g e _ h oiufr sa)p:t
                  . r o o m s   >   0 : 
                                    r e t uirfn  aFpatl.sreo
                                    o m s   <   c o n f i g .egxecte(p"tm i(nV_arlouoemEsr"r,o r0,) :T yrpeetEurrrno rF)a:l
                                    s e 
                                                             i fp aaspst . r#o oאםm sאי ן >"""
Yad2 Scraper - Map API with image/location support
"""
import requests
import logging
import math
import time
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

YAD2_MAP_API = "https://gw.yad2.co.il/realestate-feed/rent/map"
YAD2_ITEM_URL = "https://www.yad2.co.il/realestate/item/tel-aviv-area/{token}"
TEL_AVIV_BBOX = "32.029253,34.734553,32.146082,34.860195"

# חוף הים - קוארדינטות מרכזיות של קו החוף בת"א (כ-34.76 מזרח)
# קו החוף של ת"א נמצא בסביבות lon=34.758-34.763
BEACH_LON = 34.761  # קו הרוחב של החוף

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.yad2.co.il",
    "Referer": "https://www.yad2.co.il/realestate/rent/tel-aviv-area",
}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """מחשב מרחק בק"מ בין שתי נקודות (Haversine formula)"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


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
    lat: float = 0.0
    lon: float = 0.0
    distance_to_beach_km: float = -1.0
    has_mamad: bool = False

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

            # קוארדינטות
            coords = addr.get("coords", {})
            lat = float(coords.get("lat", 0) or 0)
            lon = float(coords.get("lon", 0) or 0)

            # מרחק מהחוף (רק אם יש קוארדינטות)
            dist_beach = -1.0
            if lat and lon:
                # החוף של ת"א: lat ~ 32.08 (בממוצע), lon ~ 34.761
                # מחשבים מרחק רק על ציר הרוחב (מזרח-מערב)
                # כי החוף הוא קו מאונך לגמרי
                dist_beach = haversine_km(lat, lon, lat, BEACH_LON)

            # ממ"ד — בודק כמה מקומות אפשריים ב-API
            has_mamad = False
            # Yad2 API: additionalDetails may have safeRoom/shelter
            if details.get("safeRoom") or details.get("shelter"):
                has_mamad = True
            # Also check metaData.amenities / features
            meta_raw = item.get("metaData", {})
            amenities = meta_raw.get("amenities", []) or meta_raw.get("features", [])
            if isinstance(amenities, list):
                for a in amenities:
                    a_str = str(a).lower() if not isinstance(a, dict) else str(a.get("key", "")).lower()
                    if "mamad" in a_str or "saferoom" in a_str or "safe_room" in a_str or "shelter" in a_str:
                        has_mamad = True
                        break
            # Also check in raw item for common Yad2 keys
            if item.get("shelter") or item.get("safeRoom") or item.get("mampiMemad"):
                has_mamad = True
            # Check boolean flags in additionalDetails
            for key in ["hasShelter", "hasMamad", "has_mamad", "mampiMemad", "safeRoom", "safe_room"]:
                if details.get(key):
                    has_mamad = True
                    break

            meta = item.get("metaData", {})
            description = str(meta.get("description", ""))

            # תמונות - הAPI מחזיר אותן ב-metaData
            image_url = None
            cover = meta.get("coverImage", "")
            if cover:
                image_url = cover
            else:
                images_list = meta.get("images", [])
                if images_list:
                    image_url = images_list[0]

            contact = item.get("contactInfo", {})
            contact_name = str(contact.get("contactName", ""))
            phone_obj = contact.get("phone1", {})
            contact_phone = str(phone_obj.get("phoneNumber", "") if isinstance(phone_obj, dict) else "")

            # נסה כמה שדות תאריך אפשריים מה-API של יד2
            date_added = str(
                item.get("date_added")
                or item.get("updatedAt")
                or item.get("DateOfEntry")
                or item.get("date")
                or item.get("createdAt")
                or datetime.now().isoformat()
            )
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
                lat=lat,
                lon=lon,
                distance_to_beach_km=dist_beach,
                has_mamad=has_mamad,
            )
        except Exception as e:
            logger.error(f"Error parsing item: {e}")
            return None

    def _filter_apartment(self, apt: "Apartment") -> bool:
        config = self.config

        if apt.price > 0:
            if apt.price < config.get("min_price", 0): return False
            if apt.price > config.get("max_price", 999999): return False
        if apt.rooms > 0:
            if apt.rooms < config.get("min_rooms", 0): return False
            if apt.rooms > config.get("max_rooms", 99): return False
        if apt.area_sqm > 0 and config.get("min_area_sqm"):
            if apt.area_sqm < config["min_area_sqm"]: return False

        # פילטר מרחק מהחוף
        max_beach_km = config.get("max_distance_from_beach_km", 0)
        if max_beach_km and max_beach_km > 0 and apt.distance_to_beach_km >= 0:
            if apt.distance_to_beach_km > max_beach_km:
                return False

        # פילטר שכונות (אם אין פילטר חוף, בודקים שכונות)
        if not max_beach_km:
            neighborhoods = config.get("neighborhoods", [])
            if neighborhoods and apt.neighborhood:
                if not any(n.strip() in apt.neighborhood for n in neighborhoods):
                    return False

        exclude = config.get("keywords_exclude", [])
        full_text = f"{apt.title} {apt.description}".lower()
        for kw in exclude:
            if kw.lower() in full_text: return False

        return True

    def scrape(self, max_pages: int = 3) -> list:
        all_apartments = []
        min_price = self.config.get("min_price", 0)
        max_price = self.config.get("max_price", 999999)
        url = (
            f"{YAD2_MAP_API}"
            f"?city=5000&area=1&region=3"
            f"&minRooms={self.config.get('min_rooms', 2)}"
            f"&maxRooms={self.config.get('max_rooms', 4)}"
            f"&minPrice={min_price}"
            f"&maxPrice={max_price}"
            f"&zoom=11"
            f"&bBox={TEL_AVIV_BBOX}"
        )

        # User-Agent rotation to reduce blocking
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        ]

        logger.info(f"Fetching Yad2 map API...")
        for attempt in range(3):
            try:
                if attempt > 0:
                    wait = 5 + attempt * 5  # 10s, 15s
                    time.sleep(wait)
                    logger.info(f"Retry {attempt}/2 (waited {wait}s)...")

                # Rotate user agent per attempt
                self.session.headers["User-Agent"] = user_agents[attempt % len(user_agents)]

                response = self.session.get(url, timeout=30)
                logger.info(f"Response status: {response.status_code}")

                if response.status_code == 403:
                    logger.warning("Got 403 Forbidden — Yad2 is blocking this IP")
                    continue
                if response.status_code == 429:
                    logger.warning("Got 429 Rate Limited — waiting longer...")
                    time.sleep(30)
                    continue

                response.raise_for_status()

                if not response.content or len(response.content) < 10:
                    logger.warning(f"Empty/tiny response ({len(response.content)} bytes) on attempt {attempt+1}")
                    continue

                data = response.json()
                markers = data.get("data", {}).get("markers", [])
                yad1_markers = data.get("data", {}).get("yad1Markers", [])
                all_markers = markers + yad1_markers

                if not all_markers:
                    logger.warning(f"API returned 0 markers on attempt {attempt+1}, retrying...")
                    continue

                logger.info(f"API returned {len(all_markers)} listings")
                with_images = sum(1 for m in all_markers if m.get("metaData", {}).get("coverImage"))
                logger.info(f"Items with images: {with_images}/{len(all_markers)}")

                for item in all_markers:
                    apt = self._parse_marker(item)
                    if apt and self._filter_apartment(apt):
                        all_apartments.append(apt)

                max_beach = self.config.get("max_distance_from_beach_km", 0)
                logger.info(f"After filters (beach:{max_beach}km): {len(all_apartments)} apartments")
                break

            except requests.RequestException as e:
                logger.error(f"Network error: {e}")
            except ValueError as e:
                logger.error(f"JSON parse error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error: {e}")

        logger.info(f"Total apartments found: {len(all_apartments)}")
        return all_apartments
