"""crosswalk — the join keystone: address -> BBL.

A listing carries a human street address ("45 Wall St, #613"). A building's public
record is keyed by BBL (Borough-Block-Lot). To attach one to the other you have to
canonicalize the address on both sides so "45 Wall St" (listing) and "45 WALL STREET"
(PLUTO) collapse to the same string, then look up which BBL that string belongs to.

`normalize_address` is the finicky core — it decides what "the same address" means.
`build_crosswalk` populates a `crosswalk` table from PLUTO's one-address-per-lot data.
`bbl_for_address` is the lookup a consumer calls on a live listing.

v1 is dependency-free: PLUTO (dataset 64uk-42ks) gives ONE primary address per tax
lot, so a building with entrances on three streets only matches on the one PLUTO
picked. The fuller source is PAD (Property Address Directory) — every real + vanity
address per BBL, house-number ranges expanded — which lifts the match rate a lot. A
PAD pass is the planned v2 (see the reference approach in an internal reference); this
module deliberately ships the PLUTO-only version first so the join composes today
with zero extra data dependencies.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import re

from ..record.core import socrata
from ..record.pluto import DATASET_ID, BORO_ABBR

# Spelled-out ordinal avenues -> their number, so "FIFTH AVENUE" meets "5 AVE".
_AVES = {
    "FIRST": "1", "SECOND": "2", "THIRD": "3", "FOURTH": "4", "FIFTH": "5",
    "SIXTH": "6", "SEVENTH": "7", "EIGHTH": "8", "NINTH": "9", "TENTH": "10",
    "ELEVENTH": "11", "TWELFTH": "12",
}

# Listing-title noise that sometimes rides along in an address string.
_JUNK = [re.compile(p) for p in (
    r"\b\d+\s?BEDS?\b", r"\bSTUDIO\b", r"\b\d+\s?BR\b", r"\b\d+\s?BATH\w*\b",
    r"\bNO FEE\b", r"\bFURNISHED\b", r"\bDUPLEX\b",
)]

# Street-type suffixes -> the abbreviation PLUTO uses. Applied after periods are
# stripped, so "BLVD." and "BOULEVARD" both land on "BLVD".
_SUFFIX = [
    (" STREET", " ST"), (" AVENUE", " AVE"), (" BOULEVARD", " BLVD"),
    (" PLACE", " PL"), (" ROAD", " RD"), (" DRIVE", " DR"), (" LANE", " LN"),
    (" TERRACE", " TERR"), (" PARKWAY", " PKWY"), (" COURT", " CT"),
    (" SQUARE", " SQ"), (" HIGHWAY", " HWY"), (" TURNPIKE", " TPKE"),
]

# Directionals -> single letter. "WEST 26 STREET" and "W 26TH ST" must converge.
_DIRECTIONAL = [
    (r"\bEAST\b", "E"), (r"\bWEST\b", "W"), (r"\bNORTH\b", "N"), (r"\bSOUTH\b", "S"),
]

# Trailing unit/apt portion: everything from the first unit keyword (or a `#`) to the
# end of the string. `#` gets its own arm because there's no word boundary before it.
_UNIT_TAIL = re.compile(r"\b(APARTMENT|APT|UNIT|STE|SUITE|FL|FLOOR|RM|ROOM)\b.*$|#.*$")

# Ordinal suffix on a number: 26TH -> 26, 3RD -> 3.
_ORDINAL = re.compile(r"(\d+)(ST|ND|RD|TH)\b")


def normalize_address(s):
    """Canonicalize a NYC street address for matching. Returns "" if the input can't
    be turned into a plausible house-number + street (so callers can skip it).

    The rules, in order: uppercase; drop commas/periods; strip listing-title junk;
    fold spelled-out ordinal avenues (FIFTH->5) and directionals (WEST->W); standardize
    street-type suffixes (STREET->ST); strip the unit/apt tail; drop ordinal suffixes
    on numbers (26TH->26); collapse whitespace.

    A valid result starts with a digit (a house number) and contains a letter (a street
    name) — this rejects bare units, PO boxes, and empty rows.
    """
    if not s:
        return ""
    a = s.upper().strip()
    a = re.sub(r"[,.]", " ", a)              # "BLVD." -> "BLVD "  ,  "45 Wall St, #6" -> "45 WALL ST  #6"
    for rx in _JUNK:
        a = rx.sub(" ", a)
    for word, num in _AVES.items():
        a = re.sub(r"\b" + word + r"\b", num, a)
    for pat, rep in _DIRECTIONAL:
        a = re.sub(pat, rep, a)
    for long, short in _SUFFIX:
        a = a.replace(long, short)
    a = _UNIT_TAIL.sub("", a)                # cut "APARTMENT 1816", "APT 6B", "#613", ...
    a = _ORDINAL.sub(r"\1", a)               # "26TH" -> "26"
    a = re.sub(r"\s+", " ", a).strip()
    if len(a) < 5 or not a[0].isdigit() or not re.search(r"[A-Z]", a):
        return ""
    return a


def _ensure_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crosswalk (
            norm_address TEXT NOT NULL,
            bbl          TEXT NOT NULL,
            borough      TEXT,
            zipcode      TEXT,
            PRIMARY KEY (norm_address, bbl)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_crosswalk_addr ON crosswalk(norm_address)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_crosswalk_zip  ON crosswalk(zipcode)")


def build_crosswalk(conn, limit=None, where=None):
    """Populate the `crosswalk` table from PLUTO (one primary address per tax lot).

    Pulls address+bbl+borough+zipcode from dataset 64uk-42ks via the `socrata` helper,
    normalizes each address, and upserts (norm_address, bbl, borough, zipcode). Returns
    the number of crosswalk rows written.

    `limit` caps rows fetched from PLUTO (sample instead of all ~860k lots). `where` is
    an optional raw SoQL clause — e.g. scope to the zipcodes you actually hold listings
    in, which is both faster and the realistic production pattern (PLUTO ordered by bbl
    otherwise starts on the harbor islands, which overlap no real listing).

    NOTE: PLUTO is one address per lot. PAD is the fuller source (every address per BBL,
    ranges expanded); a PAD pass is the planned v2 to raise the match rate.
    """
    _ensure_table(conn)
    select = "bbl,address,borough,zipcode"
    rows = socrata(DATASET_ID, select=select, where=where, order="bbl", limit=limit)
    for r in rows:
        norm = normalize_address(r.get("address"))
        if not norm:
            continue
        try:
            bbl = f"{int(float(r.get('bbl'))):010d}"
        except (TypeError, ValueError):
            continue
        borough = BORO_ABBR.get(r.get("borough"), r.get("borough"))
        conn.execute(
            "INSERT OR IGNORE INTO crosswalk (norm_address, bbl, borough, zipcode) "
            "VALUES (?,?,?,?)",
            (norm, bbl, borough, r.get("zipcode")),
        )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM crosswalk").fetchone()[0]


def bbl_for_address(conn, address, zipcode=None):
    """Resolve a raw listing address to a BBL via the crosswalk, or None if unmatched.

    Normalizes the input the same way the crosswalk was built, then looks it up. When a
    `zipcode` is supplied it disambiguates first (two boroughs can share a street name);
    if the zip-scoped lookup misses, it falls back to an address-only match so a missing
    or slightly-off zip doesn't cost a real hit.
    """
    norm = normalize_address(address)
    if not norm:
        return None
    if zipcode:
        row = conn.execute(
            "SELECT bbl FROM crosswalk WHERE norm_address=? AND zipcode=? LIMIT 1",
            (norm, str(zipcode)),
        ).fetchone()
        if row:
            return row[0]
    row = conn.execute(
        "SELECT bbl FROM crosswalk WHERE norm_address=? LIMIT 1", (norm,)
    ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Self-tests + live demo. `python -m pricefixed.engine.crosswalk` runs both:
# the normalization asserts (offline, instant) then the live PLUTO join proof.
# ---------------------------------------------------------------------------
def _self_test():
    cases = [
        # (raw, expected normalized)
        ("45 Wall St, #613",              "45 WALL ST"),
        ("55 WALL STREET",                "55 WALL ST"),
        ("200 W 26th St",                 "200 W 26 ST"),
        ("200 WEST 26 STREET",            "200 W 26 ST"),
        ("104-60 Queens Blvd",            "104-60 QUEENS BLVD"),
        ("51-27 QUEENS BLVD.",            "51-27 QUEENS BLVD"),
        ("4-75 48th Avenue 205",          "4-75 48 AVE 205"),   # trailing bare unit survives (no keyword) — a known miss source
        ("343 Gold Street Apartment 1816","343 GOLD ST"),
        ("250 West 50th St",              "250 W 50 ST"),
        ("1 Fifth Avenue, Apt 12B",       "1 5 AVE"),
        ("15 BROAD STREET",               "15 BROAD ST"),
        ("100 Willoughby Street",         "100 WILLOUGHBY ST"),
        ("36 East 3rd Street #5",         "36 E 3 ST"),
        ("",                              ""),
        ("Apt 4B",                        ""),                  # no house number -> rejected
    ]
    passed = 0
    for raw, want in cases:
        got = normalize_address(raw)
        ok = got == want
        passed += ok
        print(f"  [{'ok ' if ok else 'FAIL'}] {raw!r:38} -> {got!r}" + ("" if ok else f"   (want {want!r})"))
    print(f"\n  {passed}/{len(cases)} normalization cases passed")
    return passed == len(cases)


def _enrich_buildings(conn, bbls):
    """Top up the `buildings` record rows for a set of BBLs from live PLUTO, using the
    record layer's own upsert helper. Lets the demo show real facts even when the local
    record.db was only partially built. No-op for BBLs already present."""
    from ..record.core import upsert_building
    from ..record.pluto import _int, BORO_ABBR
    need = [b for b in bbls if not conn.execute(
        "SELECT 1 FROM buildings WHERE bbl=?", (b,)).fetchone()]
    if not need:
        return
    # PLUTO's bbl is a float-string; match on the numeric value.
    vals = ",".join(str(int(b)) for b in need)
    rows = socrata(
        DATASET_ID,
        select="bbl,borough,block,lot,address,zipcode,yearbuilt,unitsres,unitstotal,bldgclass",
        where=f"bbl in ({vals})",
    )
    for r in rows:
        try:
            bbl = f"{int(float(r.get('bbl'))):010d}"
        except (TypeError, ValueError):
            continue
        upsert_building(conn, bbl, {
            "borough": BORO_ABBR.get(r.get("borough"), r.get("borough")),
            "block": _int(r.get("block")), "lot": _int(r.get("lot")),
            "address": r.get("address"), "zipcode": r.get("zipcode"),
            "year_built": _int(r.get("yearbuilt")) or None,
            "units_res": _int(r.get("unitsres")), "units_total": _int(r.get("unitstotal")),
            "building_class": r.get("bldgclass"),
        })
    conn.commit()


def _demo(db_record="record.db", db_listings="listings.db"):
    """Prove the join composes live: build a crosswalk sample from PLUTO, then attach
    real scraped listings to their buildings' public record through it."""
    import sqlite3
    from ..record.core import init_record_db

    print("\n" + "=" * 70)
    print("  LIVE JOIN PROOF — listing address -> crosswalk -> BBL -> building facts")
    print("=" * 70)

    rconn = init_record_db(db_record)
    lconn = sqlite3.connect(db_listings)

    # 1) Pick real listings with clean, unit-free address strings. tfcornerstone keeps
    #    the unit in its own column, so its `address` is exactly what PLUTO stores.
    listings = lconn.execute(
        """
        SELECT source, address, unit_number, borough, zipcode
        FROM listings
        WHERE address IS NOT NULL AND zipcode IS NOT NULL AND zipcode != ''
          AND source = 'tfcornerstone'
        GROUP BY address            -- one row per distinct building address
        ORDER BY zipcode
        LIMIT 12
        """
    ).fetchall()
    if not listings:
        print("  no listings found — run:  python3 scrape.py --source tfcornerstone")
        return

    # 2) Build the crosswalk scoped to exactly the zips those listings sit in (one live
    #    PLUTO pull). Scoping by zip is the right lever here: an unscoped limit-by-bbl
    #    sample starts on the harbor islands and starves later boroughs, matching
    #    nothing. A few zips is still a small sample — a few thousand lots, one request.
    zips = sorted({z for (_, _, _, _, z) in listings})
    where = "zipcode in (" + ",".join(f"'{z}'" for z in zips) + ")"
    print(f"\n  building crosswalk over {len(zips)} listing zip(s): {', '.join(zips)}")
    n = build_crosswalk(rconn, where=where)      # no row cap: these few zips ARE the sample
    print(f"  crosswalk now holds {n} normalized PLUTO addresses\n")

    # 3) Resolve each listing and, on a hit, pull the building's PLUTO facts.
    hits = []
    for source, address, unit, borough, zipcode in listings:
        norm = normalize_address(address)
        bbl = bbl_for_address(rconn, address, zipcode=zipcode)
        mark = "HIT " if bbl else "miss"
        print(f"  [{mark}] {source:13} {address:34} -> {norm:26} -> {bbl or '-'}")
        if bbl:
            hits.append((address, unit, zipcode, norm, bbl))

    total = len(listings)
    print(f"\n  match rate on sample: {len(hits)}/{total} = {100*len(hits)/total:.0f}%")

    # Make sure the public-record layer actually holds the buildings we matched. In a
    # real run `build_record.py --source pluto` fills `buildings` NYC-wide; here we top
    # it up live for just the matched BBLs (via the same upsert helper the record layer
    # uses) so the listing -> BBL -> facts chain is genuinely end-to-end, not a stub.
    matched_bbls = [b for (_, _, _, _, b) in hits]
    _enrich_buildings(rconn, matched_bbls)

    examples = []
    for address, unit, zipcode, norm, bbl in hits:
        fact = rconn.execute(
            "SELECT year_built, units_total, building_class, address "
            "FROM buildings WHERE bbl=?", (bbl,)
        ).fetchone()
        if fact and len(examples) < 3:
            examples.append((address, unit, zipcode, norm, bbl, fact))

    if examples:
        print("\n  --- concrete joins (live asking-rent listing -> public building record) ---")
        for address, unit, zipcode, norm, bbl, (yb, ut, bc, baddr) in examples:
            print(f"\n  listing : {address}  (unit {unit or '-'}, zip {zipcode})")
            print(f"  norm    : {norm}")
            print(f"  BBL     : {bbl}")
            print(f"  building: PLUTO address {baddr!r}")
            print(f"            year_built={yb}  units_total={ut}  building_class={bc}")
    print()
    lconn.close()


if __name__ == "__main__":
    import sys
    print("normalize_address self-tests:")
    ok = _self_test()
    if not ok:
        print("  (some cases failed — see above)")
    if "--demo" in sys.argv or len(sys.argv) == 1:
        _demo()
