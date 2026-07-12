"""
pricefixed.engine.dedupe — collapse listings from multiple sources into one
row per physical apartment.

The `listings` table is one row per (source, source_id) — the natural key of
"this exact ad on this exact site". But two ads can point at the same real
apartment: the classic case here is a broker marketplace (`nooklyn`)
re-surfacing a unit that a landlord-direct feed (`stuytown`, `avalonbay`,
`glenwood`, ...) already carries under its own listing id, or the same
landlord's own feed handing the same unit a new source_id after a re-list.

This module never touches `listings` — that table stays the raw, honest
record of what every source actually said (that's load-bearing: price
history and pull_log key off it). Instead it writes a mapping table,
`unit_dedup`, from a stable `unit_id` to every (source, source_id) that
looks like the same physical unit, with exactly one row per unit flagged
`is_canonical=1` — the row a downstream consumer should show as "the"
listing for that unit. A `canonical_listings` view joins that flag back
onto `listings` for convenience.

Matching key — `unit_key()`:
    normalized address (pricefixed.engine.crosswalk.normalize_address)
    + normalized unit label (this module's `normalize_unit`)
    + bedroom count

Both the address AND the unit label must normalize to something non-empty
to enter a group. Grouping on address alone (no unit) would silently merge
different apartments in the same building — worse than under-matching. A
listing with a blank/unparseable unit or address gets its own singleton
unit_id instead of being dropped or guessed into a cluster. This mirrors
the crosswalk's own honesty rule: `normalize_address()` returns "" rather
than a guess when it can't find a house number, and this module treats ""
the same way on either side of the key — no key, no group, no fabricated
match.

Known limitation (documented, not hidden): unit-label formats genuinely
differ across sources — StuyTown's API hands back a bare number ("1816"),
some AppFolio-style feeds hand back "#204" or "Apt 204". `normalize_unit`
strips the common noise, but if two sources describe the same unit with
formats it can't reconcile (e.g. a floor+door scheme on one side and a
sequential number on the other), they land as two singletons rather than
one merged cluster — a false negative, not a false positive. This module
is deliberately biased toward under-merging: showing the same apartment
twice is a nuisance, silently splicing two different apartments into one
canonical row is a lie about someone's home.

Canonical-pick rule, once a cluster has 2+ rows (first predicate that
discriminates wins):
    1. landlord-direct over broker marketplace. `MARKETPLACE_SOURCES` is the
       explicit list of sources that are marketplaces rather than a
       landlord's own system; today that's just `nooklyn`. A landlord's own
       feed is the ground truth for its own units; a marketplace re-listing
       is a copy of somebody else's ground truth.
    2. most complete row — highest count of non-null/non-empty
       `LISTING_FIELDS`. More populated fields usually means a more careful
       or more recent scrape of that same ad.
    3. most recently seen (`last_seen`) — freshness proxy for "still
       accurate" (price, availability drift over time).
    4. (source, source_id) alphabetical — deterministic tie-break so
       re-running `build_units()` against unchanged data always picks the
       same winner.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from ..core import LISTING_FIELDS
from .crosswalk import normalize_address

# Sources known to be broker marketplaces rather than a landlord/property
# manager's own direct feed. Everything else under pricefixed/adapters/ pulls
# straight from the entity that actually manages the building, so it's the
# ground truth for its own units. Extend this set if a future adapter is
# added for another marketplace (StreetEasy, Zillow, ...).
MARKETPLACE_SOURCES = {"nooklyn"}

# Unit-label noise words a source sometimes leaves in (StuyTown/AppFolio-style
# feeds vary on whether the adapter already stripped these — normalize either
# way so "APT 6B", "Unit: 6B", and "6B" all converge).
_UNIT_WORD = re.compile(r"\b(APT|APARTMENT|UNIT|STE|SUITE|FL|FLOOR|RM|ROOM|NO)\b\.?")
_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def normalize_unit(unit):
    """Canonicalize a unit/apt label for matching across sources.

    Uppercases, strips common unit-keyword noise, drops every remaining
    non-alphanumeric character (so '#6B', 'Unit 6B', and '6B' converge), and
    strips leading zeros on a purely-numeric label (so '06' and '6'
    converge). Returns "" for missing/blank input — callers must treat ""
    as "no usable unit label", not as a match key.
    """
    if not unit:
        return ""
    u = str(unit).upper()
    u = _UNIT_WORD.sub("", u)
    u = _NON_ALNUM.sub("", u)
    if u.isdigit():
        u = str(int(u)) if u else ""
    return u


def _beds_key(bedrooms):
    """Compact string for a bedroom count: None -> "" (unknown — widens the
    key rather than forcing a spurious match), else a value where 1 and 1.0
    collapse to the same string."""
    if bedrooms is None:
        return ""
    try:
        return f"{float(bedrooms):g}"
    except (TypeError, ValueError):
        return ""


def unit_key(listing):
    """Stable string key for 'this physical apartment', or None if the
    listing doesn't carry enough to safely group — no parseable address, or
    no unit label (see module docstring for why a bare address never groups
    alone). `listing` is any mapping with at least address/unit_number/
    bedrooms keys (a sqlite3.Row-as-dict or a plain dict both work)."""
    addr = normalize_address(listing.get("address"))
    unit = normalize_unit(listing.get("unit_number"))
    if not addr or not unit:
        return None
    return f"{addr}::{unit}::beds={_beds_key(listing.get('bedrooms'))}"


def _unit_id(key):
    """Short deterministic id for a unit_key, so the mapping table's join
    column doesn't carry the full (potentially long) key text."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _ensure_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS unit_dedup (
            unit_id      TEXT NOT NULL,
            unit_key     TEXT NOT NULL,
            source       TEXT NOT NULL,
            source_id    TEXT NOT NULL,
            is_canonical INTEGER NOT NULL DEFAULT 0,
            built_at     TEXT NOT NULL,
            PRIMARY KEY (source, source_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_unit_dedup_unit ON unit_dedup(unit_id)")
    # A convenience read: "the" listing per unit, joined back onto the raw
    # table. `listings` itself is never mutated — this is purely a view.
    conn.execute(
        """
        CREATE VIEW IF NOT EXISTS canonical_listings AS
        SELECT l.*, d.unit_id, d.unit_key
        FROM listings l
        JOIN unit_dedup d ON d.source = l.source AND d.source_id = l.source_id
        WHERE d.is_canonical = 1
        """
    )
    conn.commit()


def _fetch_dicts(conn, sql, params=()):
    """Run a query and return rows as plain dicts, without touching the
    connection's row_factory (callers may share `conn` with other code that
    expects tuples)."""
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _completeness(row):
    """Count of LISTING_FIELDS this row has a non-null, non-empty value for
    — the tie-break proxy for 'more careful/complete scrape of this ad'."""
    n = 0
    for f in LISTING_FIELDS:
        v = row.get(f)
        if v not in (None, "", []):
            n += 1
    return n


def _last_seen_ts(row):
    ls = row.get("last_seen")
    try:
        return datetime.strptime(ls, "%Y-%m-%d %H:%M:%S").timestamp()
    except (TypeError, ValueError):
        return 0.0


def _rank(row):
    """Sort key for picking the canonical row within a unit's candidates —
    lower sorts first. See the 'Canonical-pick rule' in the module docstring
    for what each term means and why it's in this order."""
    is_marketplace = 1 if row.get("source") in MARKETPLACE_SOURCES else 0
    return (
        is_marketplace,          # 0 = landlord-direct wins over 1 = marketplace
        -_completeness(row),     # most complete row wins (most negative = most fields)
        -_last_seen_ts(row),     # most recently seen wins
        row.get("source") or "",
        row.get("source_id") or "",
    )


def build_units(conn, only_active=True):
    """(Re)compute `unit_dedup` from the current `listings` table. Idempotent
    full rebuild — safe to rerun after every `scrape.py` pull; cheap because
    it only touches the small dedup table, never `listings`.

    `only_active`: restrict to status='active' rows (the realistic default —
    an inactive listing from a past pull shouldn't out-rank a live one, or
    get shown as canonical at all). Pass False to dedup the full history.

    Returns a stats dict: raw_listings, distinct_units, duplicate_units
    (units with 2+ listings mapped to them — the count that matters).
    """
    _ensure_table(conn)
    where = "status='active'" if only_active else "1=1"
    cols = ["source", "source_id"] + [f for f in LISTING_FIELDS if f != "source_id"] + ["last_seen"]
    rows = _fetch_dicts(conn, f"SELECT {','.join(cols)} FROM listings WHERE {where}")

    groups = defaultdict(list)
    for row in rows:
        key = unit_key(row)
        if key is None:
            # No usable (address, unit) pair — give it a key unique to itself
            # so it still gets a stable unit_id rather than being dropped
            # from unit_dedup entirely (every active listing should resolve
            # to *some* unit_id, even a unit of one).
            key = f"singleton::{row['source']}::{row['source_id']}"
        groups[key].append(row)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM unit_dedup")
    duplicate_units = 0
    for key, candidates in groups.items():
        uid = _unit_id(key)
        winner = min(candidates, key=_rank)
        if len(candidates) > 1:
            duplicate_units += 1
        for row in candidates:
            conn.execute(
                "INSERT INTO unit_dedup (unit_id, unit_key, source, source_id, is_canonical, built_at) "
                "VALUES (?,?,?,?,?,?)",
                (uid, key, row["source"], row["source_id"], 1 if row is winner else 0, now),
            )
    conn.commit()
    return {
        "raw_listings": len(rows),
        "distinct_units": len(groups),
        "duplicate_units": duplicate_units,
    }


def find_duplicates(conn, cross_source_only=True):
    """Return unit clusters with more than one listing mapped to them — the
    actual duplicates. Call `build_units()` first; this only reads
    `unit_dedup`.

    Each result: {"unit_id", "unit_key", "listings": [rows...]} where each
    row carries source/source_id/address/unit_number/price/bedrooms/
    is_canonical. Sorted largest cluster first.

    `cross_source_only=True` (default) keeps only clusters spanning 2+
    distinct sources — the "StuyTown unit also surfaced via a broker
    marketplace" case this module exists for. Same-source duplicates (one
    feed handing the same physical unit two different source_ids, e.g.
    after a delist/relist) are a real but different phenomenon; pass False
    to include those too.
    """
    _ensure_table(conn)
    rows = _fetch_dicts(
        conn,
        """
        SELECT d.unit_id, d.unit_key, d.source, d.source_id, d.is_canonical,
               l.address, l.unit_number, l.price, l.bedrooms, l.building_name
        FROM unit_dedup d
        JOIN listings l ON l.source = d.source AND l.source_id = d.source_id
        ORDER BY d.unit_id
        """,
    )
    clusters = defaultdict(list)
    for r in rows:
        clusters[r["unit_id"]].append(r)

    out = []
    for uid, items in clusters.items():
        if len(items) < 2:
            continue
        if cross_source_only and len({i["source"] for i in items}) < 2:
            continue
        out.append({"unit_id": uid, "unit_key": items[0]["unit_key"], "listings": items})
    out.sort(key=lambda c: len(c["listings"]), reverse=True)
    return out


# ---------------------------------------------------------------------------
# Live demo. `python -m pricefixed.engine.dedupe [db_path]` runs build_units()
# against a real listings.db (default: ./listings.db) and prints the collapse
# numbers plus a few concrete duplicate clusters, same-source and cross-source.
# ---------------------------------------------------------------------------
def _demo(db="listings.db"):
    print("\n" + "=" * 70)
    print("  DEDUPE — collapsing raw listings into distinct physical units")
    print("=" * 70)
    conn = sqlite3.connect(db)
    try:
        conn.execute("SELECT 1 FROM listings LIMIT 1")
    except sqlite3.OperationalError:
        print(f"  no listings table in {db} — run: python3 scrape.py")
        return

    stats = build_units(conn)
    print(f"\n  {stats['raw_listings']} active raw listings -> {stats['distinct_units']} distinct units")
    print(f"  {stats['duplicate_units']} of those units have 2+ listings mapped to them")

    any_dups = find_duplicates(conn, cross_source_only=False)
    cross_dups = find_duplicates(conn, cross_source_only=True)
    print(f"\n  duplicate units, any source combo : {len(any_dups)}")
    print(f"  duplicate units, cross-source only : {len(cross_dups)}")

    def show(clusters, label, n=5):
        if not clusters:
            print(f"\n  (no {label} clusters in this pull)")
            return
        print(f"\n  --- example {label} clusters ---")
        for c in clusters[:n]:
            print(f"\n  unit_key: {c['unit_key']}")
            for row in c["listings"]:
                mark = "CANON" if row["is_canonical"] else "     "
                price = f"${row['price']:,.0f}" if row["price"] is not None else "-"
                print(
                    f"    [{mark}] {row['source']:13} id={row['source_id']:12} "
                    f"{row['address'] or '-':28} #{row['unit_number'] or '-':8} {price}"
                )

    show(cross_dups, "cross-source duplicate")
    if not cross_dups:
        show(any_dups, "same-source duplicate")
    print()
    conn.close()


if __name__ == "__main__":
    import sys

    _demo(sys.argv[1] if len(sys.argv) > 1 else "listings.db")
