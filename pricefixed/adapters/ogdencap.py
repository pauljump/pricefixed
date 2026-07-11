"""Ogden Cap Properties — MRI ProspectConnect (5 Manhattan buildings).
Same ProspectConnect platform as Durst: a CSRF token + session cookie gate a POST that
returns HTML unit rows. One compiled row regex pulls unit/building/sqft/availability/rent."""
import re
import time
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor

from ..core import SourceAdapter, fetch  # noqa: F401 — fetch kept for parity/reuse

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class OgdenCapAdapter(SourceAdapter):
    name = "ogdencap"
    description = "Ogden Cap Properties — MRI ProspectConnect (5 Manhattan buildings)"

    BASE = "https://ogdencapproperties.mriprospectconnect.com"

    PROPERTIES = [
        {"code": "W1", "name": "Windsor Court",        "hood": "Murray Hill",    "boro": "Manhattan"},
        {"code": "D1", "name": "Dorchester Associates", "hood": "Upper West Side", "boro": "Manhattan"},
        {"code": "B1", "name": "The Biltmore Plaza",   "hood": "Upper West Side", "boro": "Manhattan"},
        {"code": "N1", "name": "Normandie Court",      "hood": "Upper East Side", "boro": "Manhattan"},
        {"code": "L1", "name": "One Lincoln Plaza",    "hood": "Lincoln Square",  "boro": "Manhattan"},
    ]

    # Row pattern — matches one unit's full row in the search result HTML.
    # Structure: Unit td (with span + data-alt link) → Building td → Sqft td →
    #            Available td → rent-range td → button with data-unitid + data-unit-address + data-available-date
    _ROW_RE = re.compile(
        r'data-th="Unit"[^>]*>\s*<span[^>]*>([^<]+)</span>'
        r'.*?data-alt="([^"]+)"'
        r'.*?data-th="Sqft">([\d,]+)</td>'
        r'.*?data-th="Available">([^<]+)</td>'
        r'.*?data-rent-range="([^"]+)"'
        r'.*?data-unitid="([^"]+)"'
        r'.*?data-unit-address="([^"]+)"'
        r'.*?data-available-date="([^"]+)"',
        re.DOTALL,
    )

    def _get_csrf_and_opener(self, code):
        cj = CookieJar()
        opener = build_opener(HTTPCookieProcessor(cj))
        opener.addheaders = [("User-Agent", UA)]
        url = f"{self.BASE}/Search/Index/{code}/"
        resp = opener.open(url, timeout=30)
        html = resp.read().decode("utf-8", errors="replace")

        m = re.search(r'name="__RequestVerificationToken"\s+.*?value="([^"]+)"', html)
        if not m:
            m = re.search(r'value="([^"]+)".*?name="__RequestVerificationToken"', html)
        token = m.group(1) if m else ""
        return token, opener, url

    def _search_community(self, prop):
        code = prop["code"]
        try:
            token, opener, index_url = self._get_csrf_and_opener(code)
        except Exception as e:  # noqa: BLE001
            print(f"  {prop['name']}: CSRF fetch failed — {e}")
            return []

        form_data = urlencode({
            "__RequestVerificationToken": token,
            "Community": code,
            "Bedroom": "-2",
            "ApartmentNumber": "",
        }).encode("utf-8")

        req = Request(
            f"{self.BASE}/Search/Search",
            data=form_data,
            headers={
                "User-Agent": UA,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": index_url,
            },
            method="POST",
        )
        try:
            resp = opener.open(req, timeout=30)
            html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            print(f"  {prop['name']}: search POST failed — {e}")
            return []

        return self._parse_units_html(html, prop)

    def _parse_units_html(self, html, prop):
        units = []
        for m in self._ROW_RE.finditer(html):
            (unit_num, data_alt, sqft_s, avail_disp,
             rent_range, uid, addr, avail_date) = m.groups()

            # beds/baths from data-alt: "2 Beds/2 Baths for the Flex 3 floorplan, unit 16J"
            beds = 0
            baths = 1
            bed_m = re.search(r"(\d+)\s*Bed", data_alt, re.I)
            if bed_m:
                beds = int(bed_m.group(1))
            bath_m = re.search(r"(\d+(?:\.\d+)?)\s*Bath", data_alt, re.I)
            if bath_m:
                baths = float(bath_m.group(1))

            # price: lower bound of rent range "9,890.00 – 11,665.00"
            price = None
            price_m = re.match(r"([\d,]+)", rent_range.strip())
            if price_m:
                try:
                    price = float(price_m.group(1).replace(",", ""))
                except ValueError:
                    pass

            sqft = None
            try:
                sqft = int(sqft_s.replace(",", ""))
            except ValueError:
                pass

            units.append({
                "source_id": f"ogdencap-{prop['code']}-{uid.strip()}",
                "building_name": prop["name"],
                "address": addr.strip(),
                "unit_number": unit_num.strip(),
                "bedrooms": beds,
                "bathrooms": baths,
                "price": price,
                "sqft": sqft,
                "available_date": avail_date.strip()[:10] if avail_date else None,
                "lease_terms": None,
                "amenities": None,
                "description": None,
                "floor_plan_url": None,
                "image_urls": None,
                "latitude": None,
                "longitude": None,
                "neighborhood": prop["hood"],
                "borough": prop["boro"],
                "zipcode": None,
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": None,
            })

        return units

    def pull(self):
        all_units = []
        for prop in self.PROPERTIES:
            try:
                units = self._search_community(prop)
                print(f"  {prop['name']}: {len(units)} units")
                all_units.extend(units)
            except Exception as e:  # noqa: BLE001
                print(f"  {prop['name']}: ERROR — {e}")
            time.sleep(0.5)
        return all_units
