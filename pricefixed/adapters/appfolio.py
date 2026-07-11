"""AppFolio — the property-management SaaS behind a long tail of small/mid NYC operators.

Every AppFolio customer gets the same public listings site at `{company}.appfolio.com/listings`.
The page is server-rendered HTML, but it embeds a clean JSON array to draw the Google Map:

    window.googleMap = new GoogleMap({ container: 'googlemap', markers: [ {..}, {..} ] })

Each marker is one available unit: address, rent_range, unit_specs, lat/long, listing_id, photo.
That array is the feed. The authenticated `/listings/listings.json` is 401; this public map data
is the same inventory the operator publishes to lease its units.

One shape, many subdomains — so adding the next NYC operator is a one-line COMPANIES entry, not a
new file. (The signed-in JSON API needs an account; we never touch it. Public map data only.)
"""
import json
import re
import time

from ..core import SourceAdapter, fetch


def _extract_markers(html):
    """Pull the `markers: [ ... ]` JSON array out of the page. String-aware brace/bracket
    scan so an address containing a bracket can't fool a naive depth counter."""
    key = html.find("markers:")
    if key < 0:
        return []
    i = html.find("[", key)
    if i < 0:
        return []
    depth = 0
    in_str = False
    esc = False
    end = None
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end is None:
        return []
    try:
        return json.loads(html[i:end])
    except Exception:  # noqa: BLE001 — a shape change is a down feed, not a crash
        return []


def _parse_price(rent_range):
    """'$3,300' or '$2,000 - $2,500' -> low end as int. '$0' / 'Contact' -> None."""
    if not rent_range:
        return None
    nums = re.findall(r"[\d,]+", rent_range)
    if not nums:
        return None
    val = int(nums[0].replace(",", ""))
    return val or None


def _parse_specs(specs):
    """'3 bd, 2 ba, 1,250 Sq. Ft.' -> (3, 2.0, 1250). 'Studio, 1 ba' -> (0, 1.0, None)."""
    beds = 0
    baths = None
    sqft = None
    if not specs:
        return beds, baths, sqft
    bed_m = re.search(r"(\d+)\s*bd", specs, re.I)
    if bed_m:
        beds = int(bed_m.group(1))
    elif re.search(r"studio", specs, re.I):
        beds = 0
    bath_m = re.search(r"(\d+(?:\.\d+)?)\s*ba", specs, re.I)
    if bath_m:
        baths = float(bath_m.group(1))
    sqft_m = re.search(r"([\d,]+)\s*Sq\.?\s*Ft", specs, re.I)
    if sqft_m:
        sqft = int(sqft_m.group(1).replace(",", ""))
    return beds, baths, sqft


_BOROUGHS = {
    "brooklyn": "Brooklyn",
    "bronx": "Bronx",
    "queens": "Queens",
    "staten island": "Staten Island",
    "manhattan": "Manhattan",
}


def _parse_address(addr):
    """'160 Johnson Avenue - 2A, Brooklyn, NY 11206' -> (street, unit, borough, zip)."""
    zipcode = None
    zip_m = re.search(r"\b(\d{5})\b", addr)
    if zip_m:
        zipcode = zip_m.group(1)
    borough = ""
    low = addr.lower()
    for key, name in _BOROUGHS.items():
        if key in low:
            borough = name
            break
    # These operators post NYC inventory; a bare "New York, NY" city means Manhattan.
    if not borough and re.search(r"new york,?\s*(ny|new york)", low):
        borough = "Manhattan"
    street = addr.split(",")[0].strip()
    unit = ""
    unit_m = re.search(r"(?:-|#|Apt\.?|Unit|Suite|Ste\.?)\s*([\w/]+)\s*$", street, re.I)
    if unit_m:
        unit = unit_m.group(1)
        street = street[: unit_m.start()].rstrip(" -#").strip()
    return street, unit, borough, zipcode


class AppFolioAdapter(SourceAdapter):
    name = "appfolio"
    description = "AppFolio — SaaS platform, many small/mid NYC operators (one map feed each)"

    # Each entry is one landlord on AppFolio. label + subdomain is all it takes to add another.
    # Verified NYC operators (2026-07-11): every one returned NYC-addressed units on probe.
    COMPANIES = [
        {"label": "ABJ Properties", "subdomain": "abjproperties"},   # Bronx / Manhattan / Brooklyn
        {"label": "Patoma", "subdomain": "patoma"},                  # Brooklyn (Bushwick / Bed-Stuy)
        {"label": "A&N Management (ANMRE)", "subdomain": "anmre"},    # Brooklyn
        {"label": "Downtown", "subdomain": "downtown"},              # Manhattan (Lower East Side)
    ]

    def _fetch_company(self, company):
        url = f"https://{company['subdomain']}.appfolio.com/listings/listings"
        try:
            html = fetch(url, timeout=30)
        except Exception as e:  # noqa: BLE001
            return [], str(e)

        markers = _extract_markers(html)
        if not markers:
            return [], "no markers (empty or shape changed)"

        units = []
        for m in markers:
            addr = m.get("address") or ""
            beds, baths, sqft = _parse_specs(m.get("unit_specs"))
            street, unit, borough, zipcode = _parse_address(addr)
            photo = m.get("default_photo_url")
            detail = m.get("detail_page_url")
            units.append({
                "source_id": f"appfolio-{company['subdomain']}-{m.get('listing_id')}",
                "building_name": company["label"],
                "address": street,
                "unit_number": unit,
                "bedrooms": beds,
                "bathrooms": baths,
                "price": _parse_price(m.get("rent_range")),
                "sqft": sqft,
                "available_date": None,
                "lease_terms": None,
                "amenities": None,
                "description": None,
                "floor_plan_url": (f"https://{company['subdomain']}.appfolio.com{detail}"
                                   if detail else None),
                "image_urls": json.dumps([photo]) if photo else None,
                "latitude": m.get("latitude"),
                "longitude": m.get("longitude"),
                "neighborhood": "",
                "borough": borough,
                "zipcode": zipcode,
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": json.dumps(m, default=str),
            })
        return units, None

    def pull(self):
        all_units = []
        for company in self.COMPANIES:
            units, err = self._fetch_company(company)
            if err:
                print(f"  {company['label']}: ERROR — {err}")
            elif units:
                print(f"  {company['label']}: {len(units)} units")
                all_units.extend(units)
            else:
                print(f"  {company['label']}: 0 units")
            time.sleep(0.5)
        return all_units
