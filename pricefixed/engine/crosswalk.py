"""crosswalk — the join keystone: address -> BBL.

A listing carries a human street address ("45 Wall St, #613"). A building's public
record is keyed by BBL (Borough-Block-Lot). To attach one to the other you have to
canonicalize the address on both sides so "45 Wall St" (listing) and "45 WALL STREET"
(PLUTO) collapse to the same string, then look up which BBL that string belongs to.

`normalize_address` is the finicky core — it decides what "the same address" means.
`build_crosswalk` populates a `crosswalk` table from PLUTO's one-address-per-lot data.
`bbl_for_address` is the lookup a consumer calls on a live listing.

Two passes populate the crosswalk, and they compose:

  1. `build_crosswalk` — PLUTO (dataset 64uk-42ks) gives ONE primary address per tax
     lot, so a building with entrances on three streets only matches on the one PLUTO
     picked. Fast, but leaves a real coverage gap.
  2. `build_crosswalk_pad` — PAD (Property Address Directory, NYC Open Data dataset
     bc8t-ecyu) is the fuller source: every real + vanity address per BBL, with
     house-number ranges (a lot spanning 602-606 W 57 St) expanded to one row per
     number. Augments the PLUTO pass; on the sampled listings it lifts the match rate
     from 58% to ~83% by catching the addresses PLUTO's single primary never held.

PAD ships as a flat file (pad.zip -> bobaadr.txt) rather than a SoQL endpoint, so the
PAD pass downloads + caches the public archive and filters client-side by zip (the
same scoping lever `where` gives the PLUTO pass). Method: all addresses per BBL, with
house-number ranges expanded.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
import zipfile
from urllib.request import Request, urlopen

from ..core import USER_AGENT, fetch
from ..record.core import socrata
from ..record.pluto import DATASET_ID, BORO_ABBR

# NYC Open Data "Property Address Directory" (DCP PAD). It's a downloadable file asset
# (pad.zip, ~46MB, containing bobaadr.txt) rather than a SoQL table, so the PAD pass
# fetches + caches the archive and streams it, instead of going through `socrata`.
PAD_DATASET_ID = "bc8t-ecyu"
PAD_BASE = "https://data.cityofnewyork.us"
# PAD stores the borough as a single digit; map it to the full name PLUTO rows use.
BORO_NUM = {"1": "MANHATTAN", "2": "BRONX", "3": "BROOKLYN", "4": "QUEENS", "5": "STATEN ISLAND"}

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

# Word folds where a listing's spelling differs from PLUTO's own convention but should
# converge on one token. Verified live against dataset 64uk-42ks (2026-07):
#   SAINT -> ST   PLUTO writes "ST NICHOLAS AVENUE" / "ST MARKS PLACE", never "SAINT ...".
#   FT    -> FORT PLUTO itself is inconsistent — the SAME street shows up as both
#                 "FORT HAMILTON PARKWAY" and "FT HAMILTON PARKWAY" rows. Folding both
#                 sides (source ingest AND listing lookup both call normalize_address)
#                 to one spelling merges what would otherwise be a coin-flip miss.
#   PLZ   -> PLAZA PLUTO never abbreviates Plaza ("16 RICHMAN PLAZA", "QUEENS PLAZA
#                 SOUTH") — only listings do.
_WORD_FOLD = [
    (r"\bSAINT\b", "ST"), (r"\bFT\b", "FORT"), (r"\bPLZ\b", "PLAZA"),
]

# Trailing unit/apt portion: everything from the first unit keyword (or a `#`) to the
# end of the string. `#` gets its own arm because there's no word boundary before it.
_UNIT_TAIL = re.compile(r"\b(APARTMENT|APT|UNIT|STE|SUITE|FL|FLOOR|RM|ROOM)\b.*$|#.*$")

# Ordinal suffix on a number: 26TH -> 26, 3RD -> 3.
_ORDINAL = re.compile(r"(\d+)(ST|ND|RD|TH)\b")

# A bare trailing unit number with NO keyword ("4-75 48th Avenue 205" — the "205" is an
# apartment number that rode along with no "APT"/"#" to flag it, so _UNIT_TAIL never saw
# it). Only strip a trailing number when it directly follows a recognized street-type
# word, so we never eat a legitimate numbered street ("200 W 26 ST" ends on the suffix
# word "ST", not a number) or a Queens hyphenated house number ("104-60 QUEENS BLVD" —
# the hyphen is at the START of the string, this pattern only fires at the END). The
# optional single trailing letter catches "3B"/"12F"-style bare units too.
_SUFFIX_WORDS = "ST|AVE|BLVD|PL|RD|DR|LN|TERR|PKWY|CT|SQ|HWY|TPKE|PLAZA|CIRCLE|PARK|WALK|ROW"
_BARE_UNIT_TAIL = re.compile(r"\b(" + _SUFFIX_WORDS + r")\s+\d+[A-Z]?$")


def normalize_address(s):
    """Canonicalize a NYC street address for matching. Returns "" if the input can't
    be turned into a plausible house-number + street (so callers can skip it).

    The rules, in order: uppercase; drop commas/periods; strip listing-title junk;
    fold spelled-out ordinal avenues (FIFTH->5), directionals (WEST->W), and spelling
    variants (SAINT->ST, FT->FORT, PLZ->PLAZA); standardize street-type suffixes
    (STREET->ST); strip the unit/apt tail (keyword-flagged, e.g. "APT 6B"); drop
    ordinal suffixes on numbers (26TH->26); drop a bare trailing unit number that had
    no keyword to flag it (e.g. the "205" in "48th Avenue 205"); collapse whitespace.

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
    for pat, rep in _WORD_FOLD:
        a = re.sub(pat, rep, a)
    for long, short in _SUFFIX:
        a = a.replace(long, short)
    a = _UNIT_TAIL.sub("", a)                # cut "APARTMENT 1816", "APT 6B", "#613", ...
    a = _ORDINAL.sub(r"\1", a)               # "26TH" -> "26"
    a = _BARE_UNIT_TAIL.sub(r"\1", a)        # cut a keyword-less trailing unit: "AVE 205" -> "AVE"
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


# ---------------------------------------------------------------------------
# PAD pass — the fuller address source (every address per BBL, ranges expanded).
# ---------------------------------------------------------------------------
_HND_NUM = re.compile(r"^\d+$")


def _expand_hnd(lhnd, hhnd, parity):
    """Yield the display house numbers covered by a PAD low/high range.

    Only clean numeric ranges are expanded; anything else (a lone number, a Queens
    hyphenated number like "52-41", a letter/fraction) yields the low number as-is.
    `parity` is 'O'/'E' (odd/even) when the range walks one side of the street, so we
    step by 2 to avoid inventing the wrong-parity numbers PAD deliberately skips.
    """
    lo, hi = (lhnd or "").strip(), (hhnd or "").strip()
    if not lo:
        return
    if not hi or hi == lo or not (_HND_NUM.match(lo) and _HND_NUM.match(hi)):
        yield lo
        return
    a, b = int(lo), int(hi)
    if b < a or b - a > 3000:   # guard against dirty rows blowing up into millions
        yield lo
        return
    step = 2 if parity in ("O", "E") and (a % 2) == (b % 2) else 1
    for h in range(a, b + 1, step):
        yield str(h)


def _download_pad(cache_path=None, refresh=False):
    """Fetch + cache the public PAD archive (pad.zip) from NYC Open Data; return its path.

    The blob id is read live from the dataset metadata rather than hardcoded, so a
    quarterly PAD refresh (which mints a new blob id) still resolves. A cached copy is
    reused unless `refresh=True`.
    """
    if cache_path is None:
        cache_path = os.path.join(tempfile.gettempdir(), "pricefixed_pad.zip")
    if not refresh and os.path.exists(cache_path) and os.path.getsize(cache_path) > 1_000_000:
        return cache_path
    meta = json.loads(fetch(f"{PAD_BASE}/api/views/{PAD_DATASET_ID}.json"))
    blob_id = meta.get("blobId")
    if not blob_id:
        raise RuntimeError(f"PAD dataset {PAD_DATASET_ID} exposes no downloadable blob")
    fname = meta.get("blobFilename", "pad.zip")
    url = f"{PAD_BASE}/api/views/{PAD_DATASET_ID}/files/{blob_id}?filename={fname}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=180) as resp, open(cache_path, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    return cache_path


def build_crosswalk_pad(conn, zips=None, limit=None, cache_path=None, refresh=False):
    """Augment the `crosswalk` table with PAD — every real + vanity address per BBL.

    Downloads (and caches) the public PAD archive, streams bobaadr.txt, expands each
    house-number range into individual numbers, normalizes "<number> <street>" the same
    way the PLUTO pass does, and INSERT-OR-IGNOREs (norm_address, bbl, borough, zipcode).
    Returns the number of NEW crosswalk rows PAD added (rows PLUTO already held are
    ignored, so this is the genuine lift).

    Scoping mirrors `build_crosswalk`: `zips` keeps only rows in those zipcodes (the
    realistic pattern — build over exactly the zips you hold listings in, a small slice
    of the ~1M-row file), and `limit` caps how many new rows to write. PAD is a flat
    file, so both filters are applied client-side while streaming.

    BBL is assembled from PAD's boro+block+lot (boro 1 digit + block 5 + lot 4 -> the
    canonical 10-digit BBL). Only addrtype '' (real) and 'V' (vanity) rows carry a
    house-number range; NAP complex/simplex name rows are skipped here.
    """
    _ensure_table(conn)
    zipset = {str(z) for z in zips} if zips else None
    path = _download_pad(cache_path=cache_path, refresh=refresh)
    added = 0
    with zipfile.ZipFile(path) as z, z.open("bobaadr.txt") as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="latin-1"))
        header = next(reader)
        col = {k: header.index(k) for k in
               ("boro", "block", "lot", "lhnd", "hhnd", "stname", "addrtype", "parity", "zipcode")}
        for row in reader:
            zc = row[col["zipcode"]].strip()
            if zipset is not None and zc not in zipset:
                continue
            if row[col["addrtype"]].strip() not in ("", "V"):
                continue
            boro = row[col["boro"]].strip()
            block = row[col["block"]].strip()
            lot = row[col["lot"]].strip()
            if not (boro and block and lot):
                continue
            try:
                bbl = f"{int(boro + block.zfill(5) + lot.zfill(4)):010d}"
            except ValueError:
                continue
            borough = BORO_NUM.get(boro, boro)
            stname = row[col["stname"]].strip()
            parity = row[col["parity"]].strip()
            for hnum in _expand_hnd(row[col["lhnd"]], row[col["hhnd"]], parity):
                norm = normalize_address(f"{hnum} {stname}")
                if not norm:
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO crosswalk (norm_address, bbl, borough, zipcode) "
                    "VALUES (?,?,?,?)",
                    (norm, bbl, borough, zc),
                )
                added += cur.rowcount
                if limit is not None and added >= limit:
                    conn.commit()
                    return added
    conn.commit()
    return added


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
        ("4-75 48th Avenue 205",          "4-75 48 AVE"),       # FIXED: bare trailing unit (no keyword) now dropped
        ("343 Gold Street Apartment 1816","343 GOLD ST"),
        ("250 West 50th St",              "250 W 50 ST"),
        ("1 Fifth Avenue, Apt 12B",       "1 5 AVE"),
        ("15 BROAD STREET",               "15 BROAD ST"),
        ("100 Willoughby Street",         "100 WILLOUGHBY ST"),
        ("36 East 3rd Street #5",         "36 E 3 ST"),
        ("",                              ""),
        ("Apt 4B",                        ""),                  # no house number -> rejected

        # --- non-regressions: things the bare-trailing-unit strip must NOT eat ---
        ("200 W 26th St",                 "200 W 26 ST"),       # numbered street survives (ends on "ST", not a number)
        ("200 W 26 ST",                   "200 W 26 ST"),       # already-abbreviated numbered street, same guard
        ("60 West 23rd Street",           "60 W 23 ST"),        # numbered street via ordinal fold, no suffix eaten
        ("137-58 45th Avenue",            "137-58 45 AVE"),     # Queens hyphenated house number, no trailing unit to strip
        ("104-60 Queens Blvd 4B",         "104-60 QUEENS BLVD"),# hyphen house number AND a bare trailing unit together
        ("30 W 63 ST",                    "30 W 63 ST"),        # bare numbered street with no ordinal suffix at all

        # --- new fixes: word folds (SAINT->ST, FT->FORT, PLZ->PLAZA) ---
        ("100 Saint Nicholas Avenue",     "100 ST NICHOLAS AVE"),
        ("10 Ft Hamilton Pkwy",           "10 FORT HAMILTON PKWY"),
        ("10 Fort Hamilton Parkway",      "10 FORT HAMILTON PKWY"),  # both spellings converge
        ("16 Richman Plz",                "16 RICHMAN PLAZA"),
        ("16 Richman Plaza",              "16 RICHMAN PLAZA"),

        # --- lettered avenues (already worked via the generic suffix rule; locked here) ---
        ("622 Avenue B",                  "622 AVE B"),
        ("622 AVENUE B, Apt 4",           "622 AVE B"),

        # --- apostrophes in street names survive untouched ---
        ("324 O'Gorman Avenue",           "324 O'GORMAN AVE"),

        # --- double space (a real PLUTO data quirk, e.g. "VICTORY  BLVD") collapses ---
        ("2475 Victory  Blvd",            "2475 VICTORY BLVD"),
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
    try:
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
    except sqlite3.OperationalError:
        listings = []            # fresh clone: listings.db has no listings table yet
    if not listings:
        print("  no listings found — run:  python3 scrape.py --source tfcornerstone")
        return

    # 2) Scope to exactly the zips those listings sit in. Scoping by zip is the right
    #    lever: an unscoped limit-by-bbl sample starts on the harbor islands and starves
    #    later boroughs, matching nothing. A few zips is still a small sample.
    zips = sorted({z for (_, _, _, _, z) in listings})
    where = "zipcode in (" + ",".join(f"'{z}'" for z in zips) + ")"
    total = len(listings)

    def resolve():
        """Resolve every sampled listing against the current crosswalk. Returns a dict
        norm_address -> bbl (None on a miss) keyed by the listing's raw address."""
        out = {}
        for source, address, unit, borough, zipcode in listings:
            out[address] = bbl_for_address(rconn, address, zipcode=zipcode)
        return out

    def report(label, resolved, prev=None):
        hits = sum(1 for b in resolved.values() if b)
        for source, address, unit, borough, zipcode in listings:
            bbl = resolved[address]
            mark = "HIT " if bbl else "miss"
            new = "  <- NEW via PAD" if (prev is not None and bbl and not prev.get(address)) else ""
            print(f"  [{mark}] {source:13} {address:30} -> {normalize_address(address):24} -> {bbl or '-'}{new}")
        print(f"\n  match rate ({label}): {hits}/{total} = {100*hits/total:.0f}%\n")
        return hits

    # --- PASS 1: PLUTO only (the BEFORE number) ---
    print(f"\n  building crosswalk over {len(zips)} listing zip(s): {', '.join(zips)}")
    print("\n  [pass 1] PLUTO — one primary address per lot")
    n_pluto = build_crosswalk(rconn, where=where)   # no row cap: these few zips ARE the sample
    print(f"  crosswalk holds {n_pluto} normalized PLUTO addresses\n")
    before = resolve()
    report("PLUTO only", before)

    # --- PASS 2: + PAD (the AFTER number) ---
    print("  [pass 2] + PAD — every real + vanity address per BBL, ranges expanded")
    print("  downloading/caching PAD (public NYC Open Data bc8t-ecyu, ~46MB once)...")
    added = build_crosswalk_pad(rconn, zips=zips)    # augments the same table, scoped to our zips
    n_total = rconn.execute("SELECT COUNT(*) FROM crosswalk").fetchone()[0]
    print(f"  PAD added {added} new addresses -> crosswalk holds {n_total}\n")
    after = resolve()
    report("PLUTO + PAD", after, prev=before)

    # 3) Make sure the public-record layer holds the buildings we matched, then show
    #    concrete joins — favoring the listings PLUTO alone missed and PAD newly resolved.
    matched_bbls = [b for b in after.values() if b]
    _enrich_buildings(rconn, matched_bbls)

    listing_meta = {a: (u, z) for (_, a, u, _, z) in listings}
    newly = [a for a in after if after[a] and not before.get(a)]
    ordered = newly + [a for a in after if after[a] and a not in newly]

    examples = []
    for address in ordered:
        bbl = after[address]
        fact = rconn.execute(
            "SELECT year_built, units_total, building_class, address "
            "FROM buildings WHERE bbl=?", (bbl,)
        ).fetchone()
        if fact and len(examples) < 3:
            unit, zipcode = listing_meta.get(address, (None, None))
            examples.append((address, unit, zipcode, bbl, fact, address in newly))

    if examples:
        print("  --- concrete joins (live asking-rent listing -> public building record) ---")
        for address, unit, zipcode, bbl, (yb, ut, bc, baddr), is_new in examples:
            tag = "  [PLUTO alone MISSED this — resolved via PAD]" if is_new else ""
            print(f"\n  listing : {address}  (unit {unit or '-'}, zip {zipcode}){tag}")
            print(f"  norm    : {normalize_address(address)}")
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
