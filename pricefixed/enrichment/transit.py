"""
Transit — nearest subway station and walking distance, per building.

"How far to the train?" is the first question a NYC renter asks and the one the
listing sites answer with a vague "steps to the subway!" This enricher answers it
in meters, from open data: for every building point we find the closest subway
station and how far it is, so the record can say *which* station and *how far* —
facts a listing will never volunteer when the honest number is a 12-minute walk.

Source (verified live 2026-07): MTA's "Subway Stations" dataset, id `39hk-dx4f`
on data.ny.gov — 496 stations (one row per station, the modern GTFS-backed table,
not the old per-entrance dump). The fields we use:
    stop_name        station name          ("Astoria-Ditmars Blvd")
    gtfs_latitude    point latitude        ("40.775036")
    gtfs_longitude   point longitude       ("-73.912034")
    daytime_routes   space-separated lines  ("N W")
Note this dataset lives on data.ny.gov, NOT the data.cityofnewyork.us host the
`socrata()` helper hardcodes — so we pull it with the raw `fetch` client against
the state portal's own Socrata endpoint. Same SoQL, different host.

Why brute force the nearest station? 496 stations against a borough of buildings
is a few hundred-thousand `haversine` calls — trivial, and it needs no spatial
index or third-party GIS. We load the stations once into memory, then scan them
for each building. haversine gives straight-line ("as the crow flies") meters, not
sidewalk-routed walking distance; for "is this train close?" the crow-flies number
is the honest floor (a real walk is always a bit longer), which is why we name the
column `subway_dist_m` and not `walk_time`. An enricher that needs true routed
walking time should say so in its fix recipe rather than pull in a routing engine.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import json

from .core import EnrichmentSource, buildings_with_points, haversine, upsert_enrichment
from ..core import fetch

# The state portal's Socrata endpoint. The `socrata()` helper in record/core.py is
# pinned to the *city* portal, so we can't reuse it for an MTA dataset that lives on
# the *state* portal — we hit the same .json resource path directly.
STATIONS_URL = "https://data.ny.gov/resource/39hk-dx4f.json"


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _routes(raw):
    """Normalize `daytime_routes` ("N W", "4 5 6") to a compact "N,W" / "4,5,6".
    The dataset space-separates the routes serving a station; we join on commas so
    the column reads cleanly and splits deterministically downstream. None if empty."""
    if not raw:
        return None
    parts = [p for p in str(raw).split() if p]
    return ",".join(parts) if parts else None


class TransitSource(EnrichmentSource):
    name = "transit"
    description = "nearest subway station + walking distance (MTA 39hk-dx4f)"
    join_key = "point"
    columns = ("nearest_subway", "subway_dist_m", "subway_lines")

    def _load_stations(self):
        """Pull all subway stations once into memory as (name, lat, lng, routes).
        We request only the four fields we need — a small, fast page — and drop any
        row missing coordinates (can't measure distance to a point we don't have)."""
        params = "?$select=stop_name,gtfs_latitude,gtfs_longitude,daytime_routes&$limit=5000"
        rows = json.loads(fetch(STATIONS_URL + params))
        stations = []
        for r in rows:
            lat = _float(r.get("gtfs_latitude"))
            lng = _float(r.get("gtfs_longitude"))
            if lat is None or lng is None:
                continue
            stations.append((r.get("stop_name"), lat, lng, _routes(r.get("daytime_routes"))))
        return stations

    def enrich(self, conn, limit=None, boro=None) -> int:
        stations = self._load_stations()
        if not stations:
            print("  no stations pulled — aborting")
            return 0
        print(f"  loaded {len(stations)} subway stations")

        n = 0
        for bbl, lat, lng in buildings_with_points(conn, boro=boro, limit=limit):
            # Scan every station; keep the closest. min() over a generator of
            # (distance, station) pairs beats hand-rolling the running-minimum loop.
            dist, name, routes = min(
                (haversine(lat, lng, s_lat, s_lng), s_name, s_routes)
                for (s_name, s_lat, s_lng, s_routes) in stations
            )
            upsert_enrichment(conn, bbl, {
                "nearest_subway": name,
                "subway_dist_m": int(round(dist)),
                "subway_lines": routes,
            })
            n += 1
        conn.commit()
        return n
