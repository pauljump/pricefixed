"""Glenwood Management — 26 luxury Manhattan buildings (plus one in Riverdale, Bronx).
No JSON API: each building page links to per-listing detail pages, and price is buried
in a schedule-appointment iframe URL. Two-hop scrape (building -> listing) per building."""
import re
import time

from ..core import SourceAdapter, fetch


class GlenwoodAdapter(SourceAdapter):
    name = "glenwood"
    description = "Glenwood Management — 26 luxury Manhattan buildings"

    BASE = "https://www.glenwoodnyc.com"

    BUILDINGS = [
        {"slug": "downtown/barclay-tower", "bid": "107", "name": "Barclay Tower", "addr": "10 Barclay Street", "hood": "Financial District"},
        {"slug": "downtown/liberty-plaza", "bid": "19", "name": "Liberty Plaza", "addr": "10 Liberty Street", "hood": "Financial District"},
        {"slug": "downtown/tribeca-bridge-tower", "bid": "18", "name": "Tribeca Bridge Tower", "addr": "450 North End Avenue", "hood": "Tribeca"},
        {"slug": "midtown-east/paramount-tower", "bid": "17", "name": "Paramount Tower", "addr": "240 East 39th Street", "hood": "Murray Hill"},
        {"slug": "midtown-east/the-bamford", "bid": "14", "name": "The Bamford", "addr": "333 East 56th Street", "hood": "Midtown East"},
        {"slug": "midtown-east/the-belmont", "bid": "15", "name": "The Belmont", "addr": "320 East 46th Street", "hood": "Midtown East"},
        {"slug": "midtown-east/the-bristol", "bid": "23", "name": "The Bristol", "addr": "300 East 56th Street", "hood": "Midtown East"},
        {"slug": "midtown-west/crystal-green", "bid": "35", "name": "Crystal Green", "addr": "330 West 39th Street", "hood": "Midtown West"},
        {"slug": "midtown-west/emerald-green", "bid": "109", "name": "Emerald Green", "addr": "320 West 38th Street", "hood": "Midtown West"},
        {"slug": "midtown-west/the-sage", "bid": "118", "name": "The Sage", "addr": "329 West 38th Street", "hood": "Midtown West"},
        {"slug": "riverdale/briar-hill", "bid": "20", "name": "Briar Hill", "addr": "600 West 246th Street", "hood": "Riverdale"},
        {"slug": "upper-east-side/hampton-court", "bid": "6", "name": "Hampton Court", "addr": "333 East 102nd Street", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-andover", "bid": "1", "name": "The Andover", "addr": "1675 York Avenue", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-barclay", "bid": "4", "name": "The Barclay", "addr": "1755 York Avenue", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-brittany", "bid": "3", "name": "The Brittany", "addr": "1775 York Avenue", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-cambridge", "bid": "2", "name": "The Cambridge", "addr": "500 East 85th Street", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-fairmont", "bid": "8", "name": "The Fairmont", "addr": "300 East 75th Street", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-lucerne", "bid": "9", "name": "The Lucerne", "addr": "350 East 79th Street", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-marlowe", "bid": "10", "name": "The Marlowe", "addr": "145 East 81st Street", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-pavilion", "bid": "11", "name": "The Pavilion", "addr": "500 East 77th Street", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-somerset", "bid": "12", "name": "The Somerset", "addr": "1365 York Avenue", "hood": "Upper East Side"},
        {"slug": "upper-east-side/the-stratford", "bid": "13", "name": "The Stratford", "addr": "1385 York Avenue", "hood": "Upper East Side"},
        {"slug": "upper-west-side/grand-tier", "bid": "21", "name": "Grand Tier", "addr": "1930 Broadway", "hood": "Upper West Side"},
        {"slug": "upper-west-side/hawthorn-park", "bid": "117", "name": "Hawthorn Park", "addr": "160 West 62nd Street", "hood": "Upper West Side"},
        {"slug": "upper-west-side/the-encore", "bid": "119", "name": "The Encore", "addr": "175 West 60th Street", "hood": "Upper West Side"},
        {"slug": "upper-west-side/the-regent", "bid": "22", "name": "The Regent", "addr": "45 West 60th Street", "hood": "Upper West Side"},
    ]

    def _scrape_building(self, bldg):
        """Scrape a building page for listing IDs, then fetch each listing detail."""
        url = f"{self.BASE}/properties/{bldg['slug']}/"
        try:
            html = fetch(url)
        except Exception:  # noqa: BLE001
            return []

        # Find listing IDs (lid values) in the building page
        lids = re.findall(r'[?&]lid=(\d+)', html)
        lids = list(set(lids))  # deduplicate

        if not lids:
            return []

        listings = []
        for lid in lids:
            try:
                listing = self._scrape_listing(lid, bldg)
                if listing:
                    listings.append(listing)
                time.sleep(0.3)
            except Exception as e:  # noqa: BLE001
                print(f"    lid={lid}: {e}")
        return listings

    def _scrape_listing(self, lid, bldg, lat=None, lng=None):
        """Fetch and parse a single listing detail page."""
        url = f"{self.BASE}/listing-detail/?lid={lid}"
        html = fetch(url)

        # Primary: extract price from schedule-appointment iframe URL
        price = None
        pm = re.search(
            rf'schedule-appointment-listing-today/\?lid={lid}[^"]*?price=(\d+)',
            html
        )
        if pm:
            price = int(pm.group(1))

        # Extract bed/bath from pprice elements (skip phone numbers like 212.535.0500)
        beds = None
        baths = None
        for m in re.finditer(r'class="pprice"[^>]*>([^<]+)', html):
            content = m.group(1).strip()
            if not content or re.match(r'^\d{3}\.\d{3}', content):
                continue
            # Check if it's a bed/bath string
            bed_m = re.search(r'(\d+)\s*BR', content, re.I)
            if bed_m:
                beds = int(bed_m.group(1))
            elif 'studio' in content.lower():
                beds = 0
            bath_m = re.search(r'(\d+(?:\.\d+)?)\s*Bath', content, re.I)
            if bath_m:
                baths = float(bath_m.group(1))
            # Check if it's a price string (digits with optional commas)
            if price is None and re.match(r'^[\d,]+$', content):
                price = int(content.replace(',', ''))

        # Check for convertible
        if beds is None:
            cm = re.search(r'CONV(\d)', html, re.I)
            if cm:
                beds = int(cm.group(1))

        # Extract floor plan
        fp = None
        fpm = re.search(r'glenwoodadmin\.com/webdav/images/floorplans/[^"\']+', html)
        if fpm:
            fp = "https://" + fpm.group(0)

        # Extract description
        desc = None
        dm = re.search(r'class="[^"]*listing-description[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.I)
        if dm:
            desc = re.sub(r'<[^>]+>', '', dm.group(1)).strip()

        if price is None and beds is None:
            return None  # Skip empty/broken listings

        return {
            "source_id": f"glenwood-{lid}",
            "building_name": bldg["name"],
            "address": bldg["addr"],
            "unit_number": None,
            "bedrooms": beds,
            "bathrooms": baths,
            "price": price,
            "sqft": None,
            "available_date": None,
            "lease_terms": None,
            "amenities": None,
            "description": desc,
            "floor_plan_url": fp,
            "image_urls": None,
            "latitude": None,
            "longitude": None,
            "neighborhood": bldg["hood"],
            "borough": "Manhattan" if bldg["hood"] != "Riverdale" else "Bronx",
            "zipcode": None,
            "is_flex": 0,
            "is_rent_stabilized": 0,
            "finish_level": None,
            "raw_json": None,
        }

    def pull(self):
        all_listings = []
        for bldg in self.BUILDINGS:
            listings = self._scrape_building(bldg)
            if listings:
                print(f"  {bldg['name']}: {len(listings)} listings")
            all_listings.extend(listings)
            time.sleep(0.5)
        return all_listings
