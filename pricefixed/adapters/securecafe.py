"""SecureCafe / Yardi — the multi-landlord leasing platform (RentCafe family).
One HTML availability page per portal (subdomain + property slug). Many separate
landlords (Clipper, Rudin, Westminster, Goldfarb, ...) all ride the same template,
so adding inventory is just appending a portal to PORTALS."""
import re
import time

from ..core import SourceAdapter, fetch


class SecureCafeAdapter(SourceAdapter):
    name = "securecafe"
    description = "SecureCafe/Yardi — multi-landlord leasing platform"

    # Each portal: (label, subdomain, property_slug, address, neighborhood, borough)
    # We can add more portals trivially — just need subdomain + slug
    PORTALS = [
        # Clipper Equity / Clipper Realty
        {"label": "50 Murray (Tribeca House)", "subdomain": "50murray", "slug": "50-murray",
         "address": "50 Murray Street", "hood": "Tribeca", "boro": "Manhattan"},
        {"label": "53 Park Place (Tribeca House)", "subdomain": "53parkplace", "slug": "53-park-place",
         "address": "53 Park Place", "hood": "Tribeca", "boro": "Manhattan"},
        {"label": "The Aspen", "subdomain": "theaspen", "slug": "the-aspen0",
         "address": "1955 First Avenue", "hood": "East Harlem", "boro": "Manhattan"},
        {"label": "Clover House", "subdomain": "cloverhousebk", "slug": "107-columbia-heights-brooklyn-ny-11201",
         "address": "107 Columbia Heights", "hood": "Brooklyn Heights", "boro": "Brooklyn"},
        {"label": "233 Schermerhorn", "subdomain": "233schermerhorn", "slug": "security-equity-llc",
         "address": "233 Schermerhorn Street", "hood": "Downtown Brooklyn", "boro": "Brooklyn"},
        {"label": "Tower 77", "subdomain": "tower77bk", "slug": "tower-77",
         "address": "77 Commercial Street", "hood": "Greenpoint", "boro": "Brooklyn"},
        {"label": "Prospect House", "subdomain": "prospecthousebk-rentcafewebsite", "slug": "dean-street0",
         "address": "953 Dean Street", "hood": "Crown Heights", "boro": "Brooklyn"},
        {"label": "Pacific House", "subdomain": "pacifichousebk-rentcafewebsite", "slug": "pacific-house",
         "address": "1010 Pacific Street", "hood": "Crown Heights", "boro": "Brooklyn"},
        {"label": "Flatbush Gardens", "subdomain": "flatbushgardens", "slug": "flatbush-gardens",
         "address": "1403 New York Avenue", "hood": "Flatbush", "boro": "Brooklyn"},
        {"label": "Riverwatch", "subdomain": "riverwatch", "slug": "riverwatch",
         "address": "70 Battery Place", "hood": "Battery Park City", "boro": "Manhattan"},
        {"label": "The Brewster", "subdomain": "thebrewster", "slug": "the-brewster",
         "address": "21 West 86th Street", "hood": "Upper West Side", "boro": "Manhattan"},
        {"label": "Casa Hope", "subdomain": "casahope-rentcafewebsite", "slug": "casa-hope0",
         "address": "130 Hope Street", "hood": "Williamsburg", "boro": "Brooklyn"},
        {"label": "Bedford Square", "subdomain": "bedford-square1-rentcafewebsite", "slug": "bedford-square1",
         "address": "2360 Bedford Avenue", "hood": "Flatbush", "boro": "Brooklyn"},
        {"label": "Parkside BK", "subdomain": "123parkside", "slug": "123-parkside-ave-brooklyn-ny-11226",
         "address": "125 Parkside Avenue", "hood": "Flatbush", "boro": "Brooklyn"},
        {"label": "1350 Fifteenth (NJ)", "subdomain": "1350nj", "slug": "1350-15-street",
         "address": "1350 15th Street", "hood": "Fort Lee", "boro": "NJ"},
        # Rudin Management
        {"label": "Rudin Portfolio", "subdomain": "rudin-reslisting", "slug": "rudin-management-co-inc",
         "address": "", "hood": "", "boro": "Manhattan"},
        # Westminster
        {"label": "Westminster Portfolio", "subdomain": "westminster", "slug": "westminster-management",
         "address": "", "hood": "", "boro": "Manhattan"},
        # Finkelstein-Timberger
        {"label": "FTRE Portfolio", "subdomain": "ftre-reslisting", "slug": "finkelstein-timberger-east-llc",
         "address": "", "hood": "", "boro": "Manhattan"},
        # Goldfarb
        {"label": "Goldfarb Portfolio", "subdomain": "goldfarbproperties", "slug": "goldfarb-properties",
         "address": "", "hood": "", "boro": "Manhattan"},
        # Bronstein
        {"label": "Bronstein Portfolio", "subdomain": "bronsteinproperties", "slug": "bronstein-properties-llc",
         "address": "", "hood": "", "boro": "Brooklyn"},
        # 9300 Realty
        {"label": "9300 Realty Portfolio", "subdomain": "centpropny", "slug": "century-property-management-ny",
         "address": "", "hood": "", "boro": "Manhattan"},
    ]

    def _fetch_portal(self, portal):
        """Fetch and parse one SecureCafe availability portal."""
        url = f"https://{portal['subdomain']}.securecafe.com/onlineleasing/{portal['slug']}/availableunits.aspx"
        try:
            html = fetch(url, timeout=30)
        except Exception as e:  # noqa: BLE001
            return [], str(e)

        if len(html) < 500 or "404" in html[:200]:
            return [], "404 or empty"

        units = []

        # Parse floor plan sections
        # Each section: "Floor Plan: {name} - {N} Bedroom(s), {M} Bathroom(s)"
        # followed by a table of units
        sections = re.split(r'<caption[^>]*>Apartment Details.*?Floor Plan:\s*', html, flags=re.I | re.DOTALL)

        for section in sections[1:]:
            # Extract bed/bath from section header
            beds = 0
            baths = 1
            header_m = re.match(r'([^<]+)', section)
            if header_m:
                header = header_m.group(1)
                bed_m = re.search(r'(\d+)\s*Bed', header, re.I)
                if bed_m:
                    beds = int(bed_m.group(1))
                elif 'studio' in header.lower():
                    beds = 0
                bath_m = re.search(r'(\d+(?:\.\d+)?)\s*Bath', header, re.I)
                if bath_m:
                    baths = float(bath_m.group(1))

            # Find unit rows: <th data-label='Apartment'>#UNIT</th>
            # <td data-label=Sq.Ft.>SQFT</td>
            # <td data-label='Rent'>$PRICE</td>
            for um in re.finditer(
                r"data-label='Apartment'[^>]*>#?(\w+)</th>"
                r".*?data-label=Sq\.Ft\.>(\d+)</td>"
                r".*?data-label='Rent'>\$([\d,]+)</td>",
                section, re.DOTALL
            ):
                unit_num = um.group(1)
                sqft = int(um.group(2))
                price = int(um.group(3).replace(",", ""))

                # Extract move-in date from ApplyNowClick
                avail = None
                apply_m = re.search(
                    rf"id='{re.escape(unit_num)}'.*?ApplyNowClick\([^,]+,[^,]+,[^,]+,\"([^\"]+)\"",
                    section, re.DOTALL
                )
                if apply_m:
                    avail = apply_m.group(1)

                units.append({
                    "source_id": f"sc-{portal['subdomain']}-{unit_num}",
                    "building_name": portal["label"],
                    "address": portal["address"],
                    "unit_number": unit_num,
                    "bedrooms": beds,
                    "bathrooms": baths,
                    "price": price,
                    "sqft": sqft,
                    "available_date": avail,
                    "lease_terms": None,
                    "amenities": None,
                    "description": None,
                    "floor_plan_url": None,
                    "image_urls": None,
                    "latitude": None,
                    "longitude": None,
                    "neighborhood": portal["hood"],
                    "borough": portal["boro"],
                    "zipcode": None,
                    "is_flex": 0,
                    "is_rent_stabilized": 0,
                    "finish_level": None,
                    "raw_json": None,
                })

        return units, None

    def pull(self):
        all_units = []
        for portal in self.PORTALS:
            units, err = self._fetch_portal(portal)
            if err:
                print(f"  {portal['label']}: ERROR — {err}")
            elif units:
                print(f"  {portal['label']}: {len(units)} units")
                all_units.extend(units)
            else:
                print(f"  {portal['label']}: 0 units")
            time.sleep(0.5)
        return all_units
