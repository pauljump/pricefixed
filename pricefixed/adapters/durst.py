"""Durst Organization — MRI ProspectConnect (7 Manhattan/Queens buildings).
The search results are HTML, not JSON: a CSRF token + session cookie unlock a POST that
returns unit cards. Each card exposes per-lease-term option pricing (12/18/24 months),
which is preserved as `lease_terms` — the length-of-lease steering signal."""
import json
import re
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor

from ..core import SourceAdapter, fetch  # noqa: F401 — fetch kept for parity/reuse

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class DurstAdapter(SourceAdapter):
    name = "durst"
    description = "Durst Organization — MRI ProspectConnect (7 Manhattan/Queens buildings)"

    BASE = "https://durst.mriprospectconnect.com"

    PROPERTIES = [
        {"id": "44001", "name": "VIA 57 West", "address": "625 West 57th Street", "hood": "Hell's Kitchen", "boro": "Manhattan"},
        {"id": "44301", "name": "Frank 57 West", "address": "600 West 58th Street", "hood": "Hell's Kitchen", "boro": "Manhattan"},
        {"id": "36601", "name": "Helena 57 West", "address": "601 West 57th Street", "hood": "Hell's Kitchen", "boro": "Manhattan"},
        {"id": "52501", "name": "Sven", "address": "500 West 56th Street", "hood": "Hell's Kitchen", "boro": "Manhattan"},
        {"id": "40101", "name": "EOS", "address": "100 West 31st Street", "hood": "Chelsea", "boro": "Manhattan"},
        {"id": "49501", "name": "Halletts Point 10", "address": "10 Halletts Point", "hood": "Astoria", "boro": "Queens"},
        {"id": "47701", "name": "Halletts Point 20", "address": "20 Halletts Point", "hood": "Astoria", "boro": "Queens"},
    ]

    def _get_csrf_and_cookies(self, prop_id):
        """Fetch search index page to get CSRF token and session cookies."""
        cj = CookieJar()
        opener = build_opener(HTTPCookieProcessor(cj))
        opener.addheaders = [("User-Agent", UA)]
        url = f"{self.BASE}/Search/Index/{prop_id}/"
        resp = opener.open(url, timeout=30)
        html = resp.read().decode("utf-8", errors="replace")

        # Extract __RequestVerificationToken from hidden form field
        m = re.search(r'name="__RequestVerificationToken"\s+.*?value="([^"]+)"', html)
        if not m:
            m = re.search(r'value="([^"]+)".*?name="__RequestVerificationToken"', html)
        token = m.group(1) if m else ""

        return token, cj, opener

    def _search_property(self, prop):
        """Search one property and return list of unit dicts parsed from HTML."""
        prop_id = prop["id"]
        token, cj, opener = self._get_csrf_and_cookies(prop_id)

        form_data = urlencode({
            "__RequestVerificationToken": token,
            "Community": prop_id,
            "Bedroom": "-2",        # all bedrooms
            "ApartmentNumber": "",
        }).encode("utf-8")

        req = Request(
            f"{self.BASE}/Search/Search",
            data=form_data,
            headers={
                "User-Agent": UA,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{self.BASE}/Search/Index/{prop_id}/",
            },
            method="POST",
        )
        resp = opener.open(req, timeout=30)
        html = resp.read().decode("utf-8", errors="replace")
        return self._parse_units_html(html, prop)

    def _parse_units_html(self, html, prop):
        """Parse MRI ProspectConnect search results HTML into unit dicts.

        Structure: pc-card sections contain a header with bed/bath type,
        then a table of individual units (data-unitid) with sqft, available
        date, lease terms (<option> elements), and floor plan images.

        Buildings with only waitlist units (data-unittypeid but no data-unitid)
        are rent-stabilized and have no market-rate availability.
        """
        units = []

        # Split HTML into sections by unit-type card headers
        # Each pc-card has a title like "Studio 1 Bath" or "2 Bed 2 Bath"
        sections = re.split(r'<h4\s+class="pc-card-title">', html)

        current_beds, current_baths = 0, 1

        for section in sections[1:]:  # skip preamble before first card
            # Parse bed/bath from card title
            title_m = re.match(r'(.*?)</h4>', section, re.DOTALL)
            if title_m:
                title = title_m.group(1).strip()
                if "studio" in title.lower():
                    current_beds = 0
                else:
                    bm = re.search(r'(\d+)\s*bed', title, re.I)
                    if bm:
                        current_beds = int(bm.group(1))
                btm = re.search(r'(\d+)\s*bath', title, re.I)
                if btm:
                    current_baths = int(btm.group(1))

            # Find all units in this section
            unit_rows = re.findall(
                r'data-unitid="(\d+)"(.*?)(?=data-unitid="|<h4\s|$)',
                section, re.DOTALL
            )

            for uid, block in unit_rows:
                # Available date
                avail_m = re.search(r'data-available-date="([^"]+)"', block)
                avail = avail_m.group(1) if avail_m else None

                # Unit number (data-title is the display name)
                title_m = re.search(r'data-title="([^"]+)"', block)
                unit_num = title_m.group(1) if title_m else uid

                # Sqft (handles commas like "1,020")
                sqft_m = re.search(r'data-th="Sqft"[^>]*>\s*([\d,]+)', block)
                sqft = int(sqft_m.group(1).replace(",", "")) if sqft_m else None

                # Floor plan image
                fp_m = re.search(r'data-src="(https://[^"]+)"', block)
                fp_url = fp_m.group(1) if fp_m else None

                # Lease terms from <option> elements:
                # <option value="24">24 Months (3310.00 USD)</option>
                lease_terms = []
                for om in re.finditer(
                    r'<option\s+value="(\d+)">\s*(\d+)\s+Months?\s+\(([\d,.]+)\s+USD\)',
                    block, re.I
                ):
                    term_months = int(om.group(2))
                    price_val = float(om.group(3).replace(",", ""))
                    lease_terms.append({
                        "term": f"{term_months} months",
                        "price": int(price_val)
                    })

                # Primary price = 12-month lease, or shortest available
                price = None
                if lease_terms:
                    twelve = [t for t in lease_terms if t["term"] == "12 months"]
                    price = twelve[0]["price"] if twelve else min(t["price"] for t in lease_terms)

                # Check rent stabilization (DHCR)
                dhcr_m = re.search(r'data-all-dhcr-units="True"', block)
                is_stabilized = 1 if dhcr_m else 0

                units.append({
                    "source_id": f"durst-{prop['id']}-{uid}",
                    "building_name": prop["name"],
                    "address": prop["address"],
                    "unit_number": unit_num,
                    "bedrooms": current_beds,
                    "bathrooms": current_baths,
                    "price": price,
                    "sqft": sqft,
                    "available_date": avail,
                    "lease_terms": json.dumps(lease_terms) if lease_terms else None,
                    "amenities": None,
                    "description": None,
                    "floor_plan_url": fp_url,
                    "image_urls": None,
                    "latitude": None,
                    "longitude": None,
                    "neighborhood": prop["hood"],
                    "borough": prop["boro"],
                    "zipcode": None,
                    "is_flex": 0,
                    "is_rent_stabilized": is_stabilized,
                    "finish_level": None,
                    "raw_json": None,
                })

        return units

    def pull(self):
        all_units = []
        for prop in self.PROPERTIES:
            try:
                units = self._search_property(prop)
                print(f"  {prop['name']}: {len(units)} units")
                all_units.extend(units)
            except Exception as e:  # noqa: BLE001 — one building down shouldn't kill the pull
                print(f"  {prop['name']}: ERROR — {e}")
        return all_units
