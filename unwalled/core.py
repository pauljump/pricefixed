"""
unwalled.core — the shared machinery every scraper plugs into.

An adapter's only job is to return a list of listing dicts from one landlord/source.
Everything else — HTTP, retries, the SQLite schema, upserts, price-history snapshots,
marking gone listings inactive — lives here so a new source is ~30 lines of parsing.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import json
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# The standard shape every adapter returns. Only `source_id` is required; everything
# else is best-effort. Unknown fields are fine — extra keys are ignored on write.
LISTING_FIELDS = [
    "source_id", "building_name", "address", "unit_number", "bedrooms", "bathrooms",
    "price", "sqft", "available_date", "lease_terms", "amenities", "description",
    "floor_plan_url", "image_urls", "latitude", "longitude", "neighborhood",
    "borough", "zipcode", "is_flex", "is_rent_stabilized", "finish_level", "raw_json",
]


def fetch(url, headers=None, data=None, method=None, timeout=30, retries=4):
    """HTTP GET/POST with linear backoff. Returns the response body as text."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries):
        try:
            req = Request(url, data=data, headers=hdrs, method=method)
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001 — surface only after retries
            last = e
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    if last:
        raise last
    return ""


def init_db(path):
    """Open (creating if needed) the listings database and return the connection."""
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS listings (
            source          TEXT NOT NULL,
            source_id       TEXT NOT NULL,
            building_name   TEXT,
            address         TEXT,
            unit_number     TEXT,
            bedrooms        REAL,
            bathrooms       REAL,
            price           REAL,
            sqft            REAL,
            available_date  TEXT,
            lease_terms     TEXT,   -- JSON: [{term, price}, ...]
            amenities       TEXT,   -- JSON array
            description     TEXT,
            floor_plan_url  TEXT,
            image_urls      TEXT,   -- JSON array
            latitude        REAL,
            longitude       REAL,
            neighborhood    TEXT,
            borough         TEXT,
            zipcode         TEXT,
            is_flex         INTEGER,
            is_rent_stabilized INTEGER,
            finish_level    TEXT,
            raw_json        TEXT,
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL,
            status          TEXT DEFAULT 'active',
            PRIMARY KEY (source, source_id)
        );
        CREATE INDEX IF NOT EXISTS idx_listings_source   ON listings(source);
        CREATE INDEX IF NOT EXISTS idx_listings_status   ON listings(status);
        CREATE INDEX IF NOT EXISTS idx_listings_address  ON listings(address);
        CREATE INDEX IF NOT EXISTS idx_listings_price    ON listings(price);
        CREATE INDEX IF NOT EXISTS idx_listings_bedrooms ON listings(bedrooms);

        -- Every pull writes one snapshot per listing, so price/term changes over
        -- time are recoverable. This is the history that walled gardens throw away.
        CREATE TABLE IF NOT EXISTS price_history (
            source        TEXT NOT NULL,
            source_id     TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            price         REAL,
            lease_terms   TEXT,
            status        TEXT,
            PRIMARY KEY (source, source_id, snapshot_date)
        );

        CREATE TABLE IF NOT EXISTS pull_log (
            source         TEXT NOT NULL,
            pulled_at      TEXT NOT NULL,
            listings_count INTEGER,
            new_count      INTEGER,
            updated_count  INTEGER
        );
        """
    )
    conn.commit()
    return conn


def upsert_listings(conn, listings, source):
    """Write one pull's worth of listings. Tracks first_seen/last_seen, snapshots
    price history, and flips anything not seen this run to status='inactive'."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_count = updated_count = 0

    for raw in listings:
        item = {k: raw.get(k) for k in LISTING_FIELDS if k in raw}
        item["source"] = source
        item["last_seen"] = now
        existing = conn.execute(
            "SELECT first_seen FROM listings WHERE source=? AND source_id=?",
            (source, item.get("source_id")),
        ).fetchone()
        if existing is None:
            item["first_seen"] = now
            new_count += 1
        else:
            item["first_seen"] = existing[0]
            updated_count += 1
        item["status"] = "active"

        cols = list(item.keys())
        placeholders = ",".join(["?"] * len(cols))
        updates = ",".join(
            f"{c}=excluded.{c}" for c in cols if c not in ("source", "source_id", "first_seen")
        )
        conn.execute(
            f"INSERT INTO listings ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(source, source_id) DO UPDATE SET {updates}",
            tuple(item.get(c) for c in cols),
        )
        conn.execute(
            "INSERT OR REPLACE INTO price_history "
            "(source, source_id, snapshot_date, price, lease_terms, status) VALUES (?,?,?,?,?,?)",
            (source, item.get("source_id"), today, item.get("price"), item.get("lease_terms"), "active"),
        )

    conn.execute(
        "UPDATE listings SET status='inactive' WHERE source=? AND last_seen < ?", (source, now)
    )
    conn.execute(
        "INSERT INTO pull_log (source, pulled_at, listings_count, new_count, updated_count) "
        "VALUES (?,?,?,?,?)",
        (source, now, len(listings), new_count, updated_count),
    )
    conn.commit()
    return new_count, updated_count


class SourceAdapter(ABC):
    """Base class for a single source. Subclass, set `name` + `description`, implement
    `pull()` to return a list of listing dicts (see LISTING_FIELDS)."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def pull(self) -> list[dict]:
        ...

    def run(self, conn) -> tuple[int, int]:
        print(f"\n{'=' * 60}\n  {self.name} — {self.description}\n{'=' * 60}")
        t0 = time.monotonic()
        listings = self.pull()
        dt = time.monotonic() - t0
        if not listings:
            print(f"  no listings ({dt:.1f}s)")
            return 0, 0
        new, updated = upsert_listings(conn, listings, self.name)
        print(f"  {len(listings)} listings ({new} new, {updated} updated) in {dt:.1f}s")
        return new, updated
