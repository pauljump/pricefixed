"""PLUTO (Primary Land Use Tax Lot Output) — the buildings spine.

Dataset `64uk-42ks` on NYC Open Data: one row per tax lot with its physical facts
(address, year built, unit counts, building class). We upsert it as the canonical
`buildings` row keyed by BBL. Everything else enriches on top of this.

Verified field keys (2026-07): borough (2-letter, e.g. BX), block, lot, address,
zipcode, yearbuilt, unitsres, unitstotal, bldgclass, ownername, bbl (a float-string
like "2054800111.00000000", normalized to a 10-char BBL below)."""
from ..core import fetch  # noqa: F401 — kept for parity; socrata uses it internally
from .core import RecordSource, socrata, upsert_building, boro_clause

DATASET_ID = "64uk-42ks"

# PLUTO's 2-letter borough abbreviations.
BORO_ABBR = {"MN": "MANHATTAN", "BX": "BRONX", "BK": "BROOKLYN", "QN": "QUEENS", "SI": "STATEN ISLAND"}


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def normalize_bbl(raw):
    """PLUTO stores bbl as a float-string ("2054800111.00000000"). Normalize to the
    canonical 10-digit BBL string."""
    n = _int(raw)
    return f"{n:010d}" if n is not None else None


class PlutoSource(RecordSource):
    name = "pluto"
    description = "PLUTO — the buildings spine (address, year, units, class) per BBL"

    # We only need the spine columns; selecting them keeps each page small.
    SELECT = ("bbl,borough,block,lot,address,zipcode,yearbuilt,"
              "unitsres,unitstotal,bldgclass,ownername")

    def pull(self, conn, limit=None, boro=None):
        # PLUTO spells the borough as a 2-letter abbr (BX). Scope server-side so a
        # single-borough build pulls only that borough's lots.
        where = boro_clause(boro, "borough", "abbr")
        rows = socrata(DATASET_ID, select=self.SELECT, where=where, order="bbl", limit=limit)
        n = 0
        for r in rows:
            bbl = normalize_bbl(r.get("bbl"))
            if not bbl:
                continue
            upsert_building(conn, bbl, {
                "borough": BORO_ABBR.get(r.get("borough"), r.get("borough")),
                "block": _int(r.get("block")),
                "lot": _int(r.get("lot")),
                "address": r.get("address"),
                "zipcode": r.get("zipcode"),
                "year_built": _int(r.get("yearbuilt")) or None,
                "units_res": _int(r.get("unitsres")),
                "units_total": _int(r.get("unitstotal")),
                "building_class": r.get("bldgclass"),
            })
            n += 1
        conn.commit()
        return n
