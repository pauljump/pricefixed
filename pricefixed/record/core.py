"""
pricefixed.record.core — the machinery for the public-record layer.

Where the `adapters/` side scrapes live *listings*, this side builds a canonical
*record* of every NYC apartment building and its public history, pulled fresh from
NYC Open Data (Socrata). One row per BBL in `buildings`; one row per public event
(permit filed, violation issued, sale recorded, ...) in `building_events`.

A record source's only job is to pull from one Socrata dataset and write buildings
and/or events. Everything else — HTTP (via the repo's `fetch`), pagination, the
SQLite schema, upserts, event dedup, logging — lives here so a new source is short.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import json
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import urlencode

from ..core import fetch

SOCRATA_BASE = "https://data.cityofnewyork.us/resource/{dataset_id}.json"

# Columns on the one-row-per-BBL spine. Sources set whatever subset they know;
# unknown keys are ignored on write, so the table stays extensible.
BUILDING_COLUMNS = [
    "bbl", "borough", "block", "lot", "address", "zipcode", "year_built",
    "units_res", "units_total", "building_class", "owner_name",
    "owner_business_address", "permits", "permit_last", "violations",
    "viol_last", "sales", "sales_last", "complaints", "complaints_last",
    "dob_complaints", "dob_complaints_last", "cofos", "cofo_last",
    "evictions", "eviction_last", "litigations", "litigation_last",
    "sr311", "sr311_open", "sr311_last",
    "rent_stab_units", "rent_stab_status", "rent_stab_year",
]


def socrata(dataset_id, where=None, select=None, order=None, limit=None,
            page_size=50000, app_token=None):
    """Pull rows from a Socrata dataset, paginating with $limit/$offset.

    Returns a list of dicts. `limit` caps the total rows fetched (None = all).
    `where`/`select`/`order` are raw SoQL clauses. An app token is optional — the
    API works without one at low volume — but lifts rate limits if supplied.
    """
    url_base = SOCRATA_BASE.format(dataset_id=dataset_id)
    headers = {"X-App-Token": app_token} if app_token else None
    rows: list[dict] = []
    offset = 0
    while True:
        want = page_size
        if limit is not None:
            remaining = limit - len(rows)
            if remaining <= 0:
                break
            want = min(page_size, remaining)
        params = {"$limit": want, "$offset": offset}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select
        if order:
            params["$order"] = order
        url = f"{url_base}?{urlencode(params)}"
        page = json.loads(fetch(url, headers=headers))
        if not page:
            break
        rows.extend(page)
        offset += len(page)
        # A short page means the dataset (or our filter) is exhausted.
        if len(page) < want:
            break
    return rows


# ---------------------------------------------------------------------------
# Borough scoping. The BBL's first digit IS the borough, so scoping every source
# to one borough is what lets a *complete* record be built over one geography
# (owners AND violations AND evictions all landing on the same BBLs) instead of
# a thin all-NYC sample where nothing overlaps. Each NYC dataset names the borough
# differently — a numeric boroid, a full name, a 2-letter abbr, or the BBL prefix —
# so a source translates the canonical 1–5 code into whichever form it needs.
# ---------------------------------------------------------------------------
BOROUGHS = {
    1: ("MN", "MANHATTAN"),
    2: ("BX", "BRONX"),
    3: ("BK", "BROOKLYN"),
    4: ("QN", "QUEENS"),
    5: ("SI", "STATEN ISLAND"),
}

_BORO_ALIAS = {}
for _code, (_abbr, _name) in BOROUGHS.items():
    for _k in (str(_code), _abbr, _name):
        _BORO_ALIAS[_k] = _code
_BORO_ALIAS.update({"NY": 1, "NEW YORK": 1, "KINGS": 3, "RICHMOND": 5})


def parse_boro(s):
    """Parse a user-supplied borough (MN/BX/BK/QN/SI, a full name, or 1–5) to its
    canonical 1–5 code. None stays None (no scope). Raises ValueError on garbage."""
    if s is None:
        return None
    key = str(s).strip().upper()
    if key not in _BORO_ALIAS:
        raise ValueError(
            f"unknown borough {s!r} — use one of MN/BX/BK/QN/SI, a full borough name, or 1–5"
        )
    return _BORO_ALIAS[key]


def boro_clause(boro, column, form="code"):
    """A SoQL `where` fragment scoping `column` to a borough, or None when boro is None.

    `form` picks how this dataset spells the borough:
      'code' -> "2"   (boroid / ACRIS numeric borough)
      'abbr' -> "BX"  (PLUTO 2-letter)
      'name' -> "BRONX" (HPD/DOB full name)
    """
    if not boro:
        return None
    val = {"code": str(boro), "abbr": BOROUGHS[boro][0], "name": BOROUGHS[boro][1]}[form]
    return f"{column}='{val}'"


def and_where(*clauses):
    """Join non-empty SoQL clauses with AND, or return None if there are none."""
    kept = [c for c in clauses if c]
    return " AND ".join(kept) if kept else None


def init_record_db(path):
    """Open (creating if needed) the public-record database and return the connection."""
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(
        """
        -- One row per building, keyed by BBL (Borough-Block-Lot). This is the spine
        -- every source enriches: PLUTO fills the physical facts, DOB adds permit
        -- counts, HPD adds ownership, and so on.
        CREATE TABLE IF NOT EXISTS buildings (
            bbl                    TEXT PRIMARY KEY,
            borough                TEXT,
            block                  INTEGER,
            lot                    INTEGER,
            address                TEXT,
            zipcode                TEXT,
            year_built             INTEGER,
            units_res              INTEGER,
            units_total            INTEGER,
            building_class         TEXT,
            owner_name             TEXT,
            owner_business_address TEXT,
            permits                INTEGER,
            permit_last            TEXT,
            violations             INTEGER,
            viol_last              TEXT,
            sales                  INTEGER,
            sales_last             TEXT,
            complaints             INTEGER,
            complaints_last        TEXT,
            dob_complaints         INTEGER,
            dob_complaints_last    TEXT,
            cofos                  INTEGER,
            cofo_last              TEXT,
            evictions              INTEGER,
            eviction_last          TEXT,
            litigations            INTEGER,
            litigation_last        TEXT,
            sr311                  INTEGER,
            sr311_open             INTEGER,
            sr311_last             TEXT,
            rent_stab_units        INTEGER,
            rent_stab_status       TEXT,
            rent_stab_year         INTEGER,
            first_seen             TEXT NOT NULL,
            last_seen              TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_buildings_zip     ON buildings(zipcode);
        CREATE INDEX IF NOT EXISTS idx_buildings_borough ON buildings(borough);
        CREATE INDEX IF NOT EXISTS idx_buildings_address ON buildings(address);

        -- The history timeline: one row per public event. The walled gardens throw
        -- this away; here it accumulates.
        CREATE TABLE IF NOT EXISTS building_events (
            bbl        TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT,
            source     TEXT NOT NULL,
            amount     REAL,
            party      TEXT,
            detail     TEXT
        );
        -- The logical PK is (bbl, event_type, event_date, source, COALESCE(detail,'')).
        -- SQLite can't put COALESCE in a table PRIMARY KEY, so we express the same
        -- uniqueness as an expression index — INSERT OR IGNORE then dedups on it,
        -- treating a NULL detail as '' (so events with no detail don't duplicate).
        CREATE UNIQUE INDEX IF NOT EXISTS idx_events_pk
            ON building_events(bbl, event_type, event_date, source, COALESCE(detail, ''));
        CREATE INDEX IF NOT EXISTS idx_events_bbl  ON building_events(bbl);
        CREATE INDEX IF NOT EXISTS idx_events_type ON building_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_events_date ON building_events(event_date);

        CREATE TABLE IF NOT EXISTS record_source_log (
            source    TEXT NOT NULL,
            pulled_at TEXT NOT NULL,
            rows      INTEGER
        );
        """
    )
    # The buildings spine is deliberately extensible: a source may enrich a column
    # a pre-existing db predates. `CREATE TABLE IF NOT EXISTS` won't add columns to
    # a table that already exists, so bring any older db up to the current spine by
    # adding whatever BUILDING_COLUMNS it's missing (SQLite is dynamically typed, so
    # a typeless ADD COLUMN holds both the integer counts and the text dates fine).
    existing = {row[1] for row in conn.execute("PRAGMA table_info(buildings)")}
    for col in BUILDING_COLUMNS:
        if col != "bbl" and col not in existing:
            conn.execute(f"ALTER TABLE buildings ADD COLUMN {col}")
    conn.commit()
    return conn


def upsert_building(conn, bbl, fields):
    """Insert-or-update the single row for one BBL.

    `fields` is a dict of any subset of BUILDING_COLUMNS (besides bbl); only the
    keys present are written, so a source can enrich its own columns without
    clobbering another source's. Tracks first_seen (set once) / last_seen (bumped).
    """
    if not bbl:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    item = {k: fields[k] for k in BUILDING_COLUMNS if k != "bbl" and k in fields}
    item["bbl"] = bbl
    item["last_seen"] = now

    existing = conn.execute(
        "SELECT first_seen FROM buildings WHERE bbl=?", (bbl,)
    ).fetchone()
    item["first_seen"] = existing[0] if existing else now

    cols = list(item.keys())
    placeholders = ",".join(["?"] * len(cols))
    updates = ",".join(
        f"{c}=excluded.{c}" for c in cols if c not in ("bbl", "first_seen")
    )
    conn.execute(
        f"INSERT INTO buildings ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(bbl) DO UPDATE SET {updates}",
        tuple(item[c] for c in cols),
    )


def add_events(conn, events):
    """INSERT OR IGNORE a batch of event dicts into building_events.

    Each dict may carry: bbl, event_type, event_date, source, amount, party, detail.
    The unique expression index dedups repeat pulls of the same event.
    """
    cols = ["bbl", "event_type", "event_date", "source", "amount", "party", "detail"]
    conn.executemany(
        f"INSERT OR IGNORE INTO building_events ({','.join(cols)}) "
        f"VALUES ({','.join(['?'] * len(cols))})",
        [tuple(e.get(c) for c in cols) for e in events],
    )


class RecordSource(ABC):
    """Base class for one public-record source. Subclass, set `name` + `description`,
    implement `pull(conn, limit)` to write buildings/events via the helpers above."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def pull(self, conn, limit=None, boro=None) -> int:
        """Fetch from the source and write to the db. Return rows processed.

        `boro` is a canonical 1–5 borough code (or None for all of NYC); a source
        translates it into its own dataset's borough column via `boro_clause`."""
        ...

    def run(self, conn, limit=None, boro=None) -> int:
        print(f"\n{'=' * 60}\n  {self.name} — {self.description}\n{'=' * 60}")
        t0 = time.monotonic()
        rows = self.pull(conn, limit=limit, boro=boro)
        dt = time.monotonic() - t0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO record_source_log (source, pulled_at, rows) VALUES (?,?,?)",
            (self.name, now, rows),
        )
        conn.commit()
        print(f"  {rows} rows in {dt:.1f}s")
        return rows
