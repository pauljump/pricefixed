"""
pricefixed.enrichment.core — the machinery for the context layer.

Where `adapters/` scrapes live *listings* and `record/` builds the *buildings*
spine, this layer hangs public context off each building: how far to the subway,
what flood zone it sits in, which school district, the building's energy profile,
the neighborhood's demographics. Together they answer the questions a renter
actually asks about a place, from open data owned by no one.

Every enricher joins to a building by one of three keys and writes into
`building_enrichment` (one row per BBL), which mirrors the extensible-columns
pattern of the `buildings` spine — an enricher declares the columns it fills and
`ensure_columns` adds any that a pre-existing db predates.

  join_key = "bbl"   the source is already keyed by BBL (energy disclosure).
  join_key = "point" the source is geographic; match by the building's lat/lng
                     (nearest station via `haversine`, flood/school zone via
                     `point_in_polygon`).
  join_key = "area"  the source is reported per area; match by the building's
                     community district / census tract / zip (ACS demographics).

Public sources only. This is the same category as the building record: open civic
data. The rent history and pricing model stay private, elsewhere. Keep new
enrichers on the public-data side of that line.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import math
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from ..core import fetch  # noqa: F401 — re-exported for enrichers that pull HTTP
from ..record.core import socrata, boro_clause, and_where  # noqa: F401 — shared pull helpers

# County FIPS per borough code (1–5), for composing full census GEOIDs from PLUTO's
# 6-char tract. State FIPS for New York is 36.
STATE_FIPS = "36"
COUNTY_FIPS = {1: "061", 2: "005", 3: "047", 4: "081", 5: "085"}


def init_enrichment(conn):
    """Ensure the building_enrichment table exists. Keyed 1:1 to buildings by BBL.

    Deliberately thin at birth — enrichers grow it via `ensure_columns`, exactly as
    record sources grow the buildings spine. Returns the connection for chaining."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS building_enrichment (
            bbl        TEXT PRIMARY KEY,
            first_seen TEXT NOT NULL,
            last_seen  TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS enrichment_source_log (
            source    TEXT NOT NULL,
            pulled_at TEXT NOT NULL,
            enriched  INTEGER
        )
        """
    )
    conn.commit()
    return conn


def ensure_columns(conn, columns):
    """Add any of `columns` the building_enrichment table is missing (typeless ADD
    COLUMN — SQLite is dynamically typed, so one column holds ints/floats/text fine).
    Lets an enricher own its columns without editing a central list."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(building_enrichment)")}
    for col in columns:
        if col not in existing:
            conn.execute(f"ALTER TABLE building_enrichment ADD COLUMN {col}")
    conn.commit()


def upsert_enrichment(conn, bbl, fields):
    """Insert-or-update the enrichment row for one BBL, writing only the keys present
    (so one enricher never clobbers another's columns). Tracks first/last_seen."""
    if not bbl or not fields:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    item = dict(fields)
    item["bbl"] = bbl
    item["last_seen"] = now
    existing = conn.execute(
        "SELECT first_seen FROM building_enrichment WHERE bbl=?", (bbl,)
    ).fetchone()
    item["first_seen"] = existing[0] if existing else now

    cols = list(item.keys())
    placeholders = ",".join(["?"] * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("bbl", "first_seen"))
    conn.execute(
        f"INSERT INTO building_enrichment ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(bbl) DO UPDATE SET {updates}",
        tuple(item[c] for c in cols),
    )


def buildings_with_points(conn, boro=None, limit=None):
    """Yield (bbl, lat, lng) for buildings that carry coordinates. The `point`-join
    enrichers iterate this. `boro` scopes to one borough by BBL prefix (the first BBL
    digit IS the borough), so an enricher can prove itself on a small slice."""
    where = "latitude IS NOT NULL AND longitude IS NOT NULL"
    if boro:
        where += f" AND substr(bbl,1,1)='{int(boro)}'"
    sql = f"SELECT bbl, latitude, longitude FROM buildings WHERE {where}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    yield from conn.execute(sql)


def buildings_with_areas(conn, boro=None, limit=None):
    """Yield (bbl, community_district, census_tract, zipcode) for the `area`-join
    enrichers. Same borough-by-BBL-prefix scoping as buildings_with_points."""
    where = "1=1"
    if boro:
        where += f" AND substr(bbl,1,1)='{int(boro)}'"
    sql = (f"SELECT bbl, community_district, census_tract, zipcode "
           f"FROM buildings WHERE {where}")
    if limit:
        sql += f" LIMIT {int(limit)}"
    yield from conn.execute(sql)


def census_geoid(boro_code, tract):
    """Compose the 11-digit census tract GEOID (state+county+tract) from a borough
    code (1–5) and PLUTO's 6-char tract, for joining to Census ACS. None on garbage."""
    county = COUNTY_FIPS.get(int(boro_code)) if boro_code else None
    if not county or not tract:
        return None
    t = str(tract).strip().zfill(6)
    if len(t) != 6 or not t.isdigit():
        return None
    return STATE_FIPS + county + t


# ---------------------------------------------------------------------------
# Geometry — pure-stdlib, because the whole repo is dependency-free. Good enough
# for civic data at building scale; an enricher that needs industrial-strength GIS
# should say so in its fix recipe rather than pull in shapely.
# ---------------------------------------------------------------------------
def haversine(lat1, lng1, lat2, lng2):
    """Great-circle distance in meters between two lat/lng points."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def point_in_polygon(lat, lng, ring):
    """Ray-casting point-in-polygon. `ring` is a list of (lng, lat) vertices — the
    GeoJSON coordinate order Socrata multipolygons use. Returns True if the point is
    inside. For a multipolygon, test each ring and OR the results."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-16) + xi
        ):
            inside = not inside
        j = i
    return inside


class EnrichmentSource(ABC):
    """Base class for one context source. Subclass, set `name` + `description` +
    `join_key` + `columns`, implement `enrich(conn, limit, boro)` to write via
    upsert_enrichment. `columns` is the set this source owns; run() ensures they
    exist before enrich() is called."""

    name: str = ""
    description: str = ""
    join_key: str = "bbl"          # "bbl" | "point" | "area"
    columns: tuple = ()            # building_enrichment columns this source fills

    @abstractmethod
    def enrich(self, conn, limit=None, boro=None) -> int:
        """Attach this source's context to buildings. Return the number enriched."""
        ...

    def run(self, conn, limit=None, boro=None) -> int:
        print(f"\n{'=' * 60}\n  {self.name} — {self.description}\n{'=' * 60}")
        init_enrichment(conn)
        if self.columns:
            ensure_columns(conn, self.columns)
        t0 = time.monotonic()
        n = self.enrich(conn, limit=limit, boro=boro)
        dt = time.monotonic() - t0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO enrichment_source_log (source, pulled_at, enriched) VALUES (?,?,?)",
            (self.name, now, n),
        )
        conn.commit()
        print(f"  {n} buildings enriched in {dt:.1f}s")
        return n
