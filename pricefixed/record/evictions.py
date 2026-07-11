"""NYC Marshal Evictions — the executed-eviction history.

Dataset `6z8x-wfk4` on NYC Open Data: one row per eviction a city marshal actually
*executed* (not merely filed) at a residential or commercial address. An executed
eviction is the sharpest public signal of how a building treats its tenants, and the
walled listing sites never surface it.

This dataset is keyed by a human `eviction_address` ("2565 MARION AVENUE APT 2C"), so
it's the natural second place (after DOB complaints) to *dogfood our own address->BBL
crosswalk* (`pricefixed/engine/crosswalk`): we normalize each eviction address, resolve
it to a BBL, skip the rows that don't match, and report the resolve rate at the end.
For each resolved building we (a) roll up an `evictions` count + latest `eviction_last`
date, and (b) append one `building_events` row per eviction (event_type="eviction").

NOTE (2026-07): the current dataset ALSO exposes a computed `bbl` field — the "no BBL"
premise has since changed. We deliberately resolve via the crosswalk anyway to exercise
the address join and report a genuine resolve rate; a production build could instead
prefer the dataset's own bbl. Verified keys (2026-07): eviction_address, eviction_apt_num,
eviction_zip, borough, executed_date (ISO like "2025-09-17T00:00:00.000"),
residential_commercial_ind (Residential/Commercial), ejectment, eviction_possession, bbl."""
import sqlite3

from ..core import fetch  # noqa: F401 — parity with adapter style
from ..engine.crosswalk import bbl_for_address, build_crosswalk
from .core import RecordSource, socrata, upsert_building, add_events

DATASET_ID = "6z8x-wfk4"


def iso_date(dt):
    """Marshal timestamps look like "2025-09-17T00:00:00.000" -> "2025-09-17"."""
    if not dt:
        return None
    return str(dt)[:10]


class EvictionsSource(RecordSource):
    name = "evictions"
    description = "NYC Marshal Evictions — address-resolved eviction events + per-building counts"

    SELECT = "eviction_address,eviction_apt_num,eviction_zip,borough,executed_date,residential_commercial_ind"

    def _ensure_crosswalk(self, conn, zips):
        """Make sure the crosswalk covers the zips in this sample so resolution is real.

        The crosswalk table lives in the same db; a fresh clone starts empty. We build
        (via PLUTO) only the zips we don't already hold — one scoped SoQL query, the same
        zip-scoped pattern DOB complaints uses — so the resolve rate reflects a genuine
        address->BBL match, not an empty table."""
        try:
            have = {z for (z,) in conn.execute(
                "SELECT DISTINCT zipcode FROM crosswalk WHERE zipcode IS NOT NULL")}
        except sqlite3.OperationalError:
            have = set()  # crosswalk table doesn't exist yet
        missing = [z for z in zips if z and z not in have]
        if missing:
            where = "zipcode in (" + ",".join(f"'{z}'" for z in missing) + ")"
            build_crosswalk(conn, where=where)

    def pull(self, conn, limit=None):
        rows = socrata(DATASET_ID, select=self.SELECT, order="executed_date DESC", limit=limit)
        self._ensure_crosswalk(conn, {r.get("eviction_zip") for r in rows})

        events = []
        agg: dict[str, dict] = {}
        attempted = 0   # rows with a usable address string
        resolved = 0    # rows the crosswalk turned into a BBL
        for r in rows:
            address = r.get("eviction_address")
            if not address:
                continue
            attempted += 1
            bbl = bbl_for_address(conn, address, zipcode=r.get("eviction_zip"))
            if not bbl:
                continue
            resolved += 1
            date = iso_date(r.get("executed_date"))
            apt = r.get("eviction_apt_num")
            detail = " / ".join(
                x for x in (
                    r.get("residential_commercial_ind"),
                    f"apt {apt}" if apt else None,
                ) if x
            ) or None
            events.append({
                "bbl": bbl, "event_type": "eviction", "event_date": date,
                "source": self.name, "detail": detail,
            })
            a = agg.setdefault(bbl, {"count": 0, "last": None})
            a["count"] += 1
            if date and (a["last"] is None or date > a["last"]):
                a["last"] = date

        add_events(conn, events)
        for bbl, a in agg.items():
            upsert_building(conn, bbl, {"evictions": a["count"], "eviction_last": a["last"]})
        conn.commit()

        rate = (100 * resolved / attempted) if attempted else 0.0
        print(f"  address->BBL crosswalk resolve rate: {resolved}/{attempted} = {rate:.0f}%")
        return len(events)
