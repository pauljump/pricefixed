"""portfolios — Who-Owns-What: cluster single-purpose LLCs into landlord portfolios.

Landlords hide behind one LLC per building (an LLC for 45 Wall St, a different LLC for
47 Wall St, and so on) so a per-building violation count never adds up to the pattern.
JustFix's "Who Owns What" cracked this years ago with one insight: the LLCs still share
a *registered business address* (or a head officer) because someone still has to receive
the mail and manage the buildings. HPD Registrations captures exactly that address — see
`pricefixed/record/hpd_registrations.py`, which already writes `owner_name` and
`owner_business_address` onto every building it touches.

This module is the clustering pass on top of that: read every building's
owner_name/owner_business_address off the `buildings` table already built by
`build_record.py`, normalize the business address into a stable key, group BBLs that
share it, and roll up each cluster's accountability counts (violations, evictions,
complaints, ...) that the other record sources already wrote onto those same rows. The
output is two small tables — `portfolios` (one row per landlord cluster) and
`building_portfolio` (the bbl -> portfolio_id map) — so "who owns this building, and
what's their record across everything they own" becomes one join instead of a research
project.

CLUSTERING KEY: normalized `owner_business_address` is primary, exactly like JustFix's
"business address" grouping. When a building carries no usable business address (rare,
but HPD Contacts data has gaps), it falls back to a per-building key instead of
merging into an undifferentiated catch-all bucket under the empty string — false-merging
unrelated owners would be worse than leaving them unclustered. We do NOT cluster by head
officer name; the record layer only persists one folded `owner_name` field per building
(see `_pick_owner` in hpd_registrations.py), not a separate officer identity, so a
name-only signal here would be a coin flip between "same person" and "two landlords who
both work with the same management agent." Address is the honest key we actually have.

This is a scaffold, not a claim of completeness: it only sees what HPD Registrations
already wrote, so a building whose owner was never pulled (or has no business address on
file) simply will not appear in any portfolio, rather than being guessed into one. Run it
against a record.db that has HPD registration data (`python build_record.py --source
hpd_registrations`), then `python -m pricefixed.engine.portfolios --db record.db`.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone

# The count columns on `buildings` (see pricefixed/record/core.py BUILDING_COLUMNS)
# that represent an accountability signal worth rolling up to the portfolio level.
# Mapped to the portfolio column that holds their sum.
ROLLUP_COLUMNS = {
    "violations": "total_violations",
    "evictions": "total_evictions",
    "complaints": "total_complaints",
    "dob_complaints": "total_dob_complaints",
    "litigations": "total_litigations",
    "sr311": "total_sr311",
    "sr311_open": "total_sr311_open",
    "permits": "total_permits",
    "sales": "total_sales",
    "cofos": "total_cofos",
}

# Corporate entity suffixes to strip off the *end* of an owner name so "45 WALL ST
# REALTY LLC" and "45 WALL ST REALTY, LLC" both read as "45 WALL ST REALTY". Applied
# repeatedly (some filings double up, e.g. "... LLC INC") until nothing more strips.
_ENTITY_SUFFIX = re.compile(
    r"\s+(L\s*L\s*C|L\s*L\s*P|L\s*P|P\s*L\s*L\s*C|CORP(ORATION)?|INC(ORPORATED)?|"
    r"LTD|LIMITED)\.?\s*$"
)

# Street-type words -> the abbreviation form, so "AVENUE" and "AVE" converge in a
# business address. A light version of the crosswalk's suffix table — business
# addresses aren't validated against PLUTO, so this doesn't need to be exhaustive,
# just consistent for buildings genuinely registered to the same office.
_ADDR_SUFFIX = [
    (" STREET", " ST"), (" AVENUE", " AVE"), (" BOULEVARD", " BLVD"),
    (" PLACE", " PL"), (" ROAD", " RD"), (" DRIVE", " DR"), (" LANE", " LN"),
    (" TERRACE", " TERR"), (" PARKWAY", " PKWY"), (" COURT", " CT"),
    (" SQUARE", " SQ"), (" HIGHWAY", " HWY"), (" TURNPIKE", " TPKE"),
    (" FLOOR", " FL"), (" SUITE", " STE"), (" APARTMENT", " APT"),
]
_ADDR_DIRECTIONAL = [
    (r"\bEAST\b", "E"), (r"\bWEST\b", "W"), (r"\bNORTH\b", "N"), (r"\bSOUTH\b", "S"),
]


def normalize_owner_name(name):
    """Uppercase, strip trailing corporate-entity suffixes, collapse whitespace.

    Returns "" for a falsy input. Only strips suffixes anchored at the end of the
    string (not anywhere a substring matches), so "Lincoln Realty" never loses "Inc"
    it never had.
    """
    if not name:
        return ""
    n = name.upper().strip()
    n = re.sub(r"[.,]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    while True:
        stripped = _ENTITY_SUFFIX.sub("", n).strip()
        if stripped == n:
            break
        n = stripped
    return n


def normalize_business_address(addr):
    """Canonicalize an HPD-registered business address into a stable cluster key.

    Same spirit as `pricefixed.engine.crosswalk.normalize_address` (uppercase, fold
    directionals, standardize suffixes, collapse whitespace) but deliberately looser:
    a business address is "500 3 AVE, BROOKLYN, NY, 11215" — city/state/zip and all —
    not a bare street address to be matched against PLUTO, and it isn't rejected for
    lacking a leading house number (a PO box or suite-only registration still clusters
    fine on the rest of the string). Returns "" for a falsy/unusable input.
    """
    if not addr:
        return ""
    a = addr.upper()
    a = re.sub(r"[.,#]", " ", a)
    for pat, rep in _ADDR_DIRECTIONAL:
        a = re.sub(pat, rep, a)
    for long, short in _ADDR_SUFFIX:
        a = a.replace(long, short)
    a = re.sub(r"\s+", " ", a).strip()
    return a


def _cluster_key(bbl, norm_addr):
    """The grouping key for one building: shared normalized business address when we
    have one, else a key unique to this BBL so it stands alone rather than merging
    into a false "no address on file" mega-cluster with every other gap."""
    return norm_addr if norm_addr else f"__no_address__{bbl}"


def _portfolio_id(cluster_key):
    """Deterministic id from the cluster key (not an autoincrement rowid), so rerunning
    `build_portfolios` on an unchanged db assigns the same id to the same cluster —
    that's what makes INSERT OR REPLACE idempotent instead of accumulating duplicates."""
    return "pf_" + hashlib.sha1(cluster_key.encode("utf-8")).hexdigest()[:16]


def _ensure_tables(conn):
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS portfolios (
            portfolio_id      TEXT PRIMARY KEY,
            canonical_name    TEXT,
            business_address  TEXT,
            building_count    INTEGER,
            llc_count         INTEGER,
            {", ".join(f"{col} INTEGER" for col in ROLLUP_COLUMNS.values())},
            updated_at        TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS building_portfolio (
            bbl          TEXT PRIMARY KEY,
            portfolio_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_building_portfolio_pid "
        "ON building_portfolio(portfolio_id)"
    )


def build_portfolios(conn):
    """Cluster every building's owner into landlord portfolios and materialize the
    `portfolios` + `building_portfolio` tables. Returns (portfolio_count, building_count).

    This is a full rebuild each call, not an incremental append: the tables are derived
    entirely from the current `buildings` rows, so re-running after new record sources
    have enriched more buildings (more violations, a later HPD pull, ...) reflects the
    latest state rather than compounding stale totals. Safe to call repeatedly —
    deterministic portfolio ids (hashed from the cluster key) plus a full clear-and-
    rebuild inside one transaction is what makes two consecutive runs on the same
    `buildings` data produce byte-identical output.
    """
    _ensure_tables(conn)

    cols = ["bbl", "owner_name", "owner_business_address"] + list(ROLLUP_COLUMNS)
    coalesced = ", ".join(
        f"COALESCE({c},0)" if c in ROLLUP_COLUMNS else c for c in cols
    )
    try:
        rows = conn.execute(
            f"SELECT {coalesced} FROM buildings "
            "WHERE owner_name IS NOT NULL OR owner_business_address IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []  # fresh db, buildings table not yet created

    clusters: dict[str, dict] = {}
    for row in rows:
        bbl, owner_name, owner_addr, *counts = row
        norm_addr = normalize_business_address(owner_addr)
        key = _cluster_key(bbl, norm_addr)
        c = clusters.setdefault(key, {
            "bbls": [], "owner_names": Counter(), "business_address": owner_addr or "",
            "norm_addr": norm_addr, "totals": defaultdict(int),
        })
        c["bbls"].append(bbl)
        if owner_name:
            c["owner_names"][owner_name] += 1
        # Prefer the first non-empty raw address string seen for display (they should
        # all be identical within a cluster keyed on the normalized form; a mismatch
        # would only mean two raw spellings normalized to the same key, which is the
        # whole point of normalizing).
        if owner_addr and not c["business_address"]:
            c["business_address"] = owner_addr
        for total_col, val in zip(ROLLUP_COLUMNS.values(), counts):
            c["totals"][total_col] += val

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    portfolio_rows = []
    bp_rows = []
    for key, c in clusters.items():
        pid = _portfolio_id(key)
        # canonical_name: the most common raw owner_name in the cluster (a shared
        # business address run by many single-purpose LLCs rarely has one owner_name
        # in common across all of them — that IS the pattern being surfaced — so this
        # is "the most frequent name at this address," not a claim of legal identity).
        canonical = c["owner_names"].most_common(1)[0][0] if c["owner_names"] else "(unknown owner)"
        totals = [c["totals"].get(col, 0) for col in ROLLUP_COLUMNS.values()]
        portfolio_rows.append((
            pid, canonical, c["business_address"], len(c["bbls"]), len(c["owner_names"]),
            *totals, now,
        ))
        bp_rows.extend((bbl, pid) for bbl in c["bbls"])

    with conn:
        # Full clear-and-rebuild (see docstring): derived tables, not an event log.
        conn.execute("DELETE FROM portfolios")
        conn.execute("DELETE FROM building_portfolio")
        pcols = (
            ["portfolio_id", "canonical_name", "business_address", "building_count",
             "llc_count"] + list(ROLLUP_COLUMNS.values()) + ["updated_at"]
        )
        conn.executemany(
            f"INSERT OR REPLACE INTO portfolios ({','.join(pcols)}) "
            f"VALUES ({','.join(['?'] * len(pcols))})",
            portfolio_rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO building_portfolio (bbl, portfolio_id) VALUES (?,?)",
            bp_rows,
        )
    return len(portfolio_rows), len(bp_rows)


# ---------------------------------------------------------------------------
# Live demo. `python -m pricefixed.engine.portfolios [--db record.db]` builds
# portfolios over the current record.db (topping up owner data from a small live HPD
# Registrations pull first if the db barely has any) and prints the top landlords by
# building count with their rolled-up accountability record.
# ---------------------------------------------------------------------------
def _demo(db_path="record.db", top_n=15, seed_limit=3000):
    from ..record.core import init_record_db
    from ..record.hpd_registrations import HpdRegistrationsSource

    print("\n" + "=" * 70)
    print("  WHO OWNS WHAT — clustering buildings into landlord portfolios")
    print("=" * 70)

    conn = init_record_db(db_path)
    owned = conn.execute(
        "SELECT COUNT(*) FROM buildings WHERE owner_name IS NOT NULL"
    ).fetchone()[0]
    print(f"\n  buildings with owner data on file: {owned}")

    if owned < 200:
        print(f"  too few to show real clustering — pulling a live HPD Registrations "
              f"sample (limit={seed_limit}) to seed owner_name/owner_business_address...")
        n = HpdRegistrationsSource().run(conn, limit=seed_limit)
        owned = conn.execute(
            "SELECT COUNT(*) FROM buildings WHERE owner_name IS NOT NULL"
        ).fetchone()[0]
        print(f"  seeded {n} buildings; now {owned} carry owner data")

    n_portfolios, n_buildings = build_portfolios(conn)
    print(f"\n  {n_portfolios} portfolios covering {n_buildings} buildings "
          f"(from record.db at {db_path})")

    print(f"\n  --- top {top_n} landlords by building count ---\n")
    rollup_select = ", ".join(ROLLUP_COLUMNS.values())
    top = conn.execute(
        f"""
        SELECT canonical_name, business_address, building_count, llc_count, {rollup_select}
        FROM portfolios
        WHERE building_count > 1
        ORDER BY building_count DESC
        LIMIT ?
        """,
        (top_n,),
    ).fetchall()

    if not top:
        print("  no multi-building portfolios in this sample — every owner pulled so "
              "far shows exactly one registered building. That's a real, honest result "
              "of the sample size, not a bug: rerun with a larger --seed-limit, or build "
              "record.db over a specific neighborhood's zip codes, to surface repeat "
              "landlords. No numbers are invented to make this section look busier.")
    for row in top:
        name, addr, bcount, llc_count, *totals = row
        totals_map = dict(zip(ROLLUP_COLUMNS.values(), totals))
        print(f"  {name}")
        print(f"    business address : {addr}")
        print(f"    buildings         : {bcount}  (across {llc_count} distinct LLC name(s) on file)")
        print(f"    violations        : {totals_map['total_violations']}   "
              f"evictions: {totals_map['total_evictions']}   "
              f"hpd complaints: {totals_map['total_complaints']}   "
              f"311 open: {totals_map['total_sr311_open']}")
        print()

    conn.close()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build Who-Owns-What landlord portfolios.")
    ap.add_argument("--db", default="record.db", help="record.db path (default: record.db)")
    ap.add_argument("--top", type=int, default=15, help="how many top landlords to print")
    ap.add_argument("--seed-limit", type=int, default=3000,
                     help="HPD Registrations rows to pull if the db is too sparse to cluster")
    args = ap.parse_args()
    _demo(db_path=args.db, top_n=args.top, seed_limit=args.seed_limit)
