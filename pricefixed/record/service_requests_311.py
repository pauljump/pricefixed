"""311 Service Requests — the resident-complaint history (housing slice).

Dataset `erm2-nwe9` on NYC Open Data: one row per 311 service request. This is one of
the largest open datasets in the world (30M+ rows across every agency), so pulling it
whole is neither possible nor useful here. We scope it two ways: a `$where` filter to the
housing-relevant slice (`agency='HPD'` — heat/hot water, plumbing, pests, mold, paint,
...), and we always honor `limit`. That keeps every pull bounded and on-topic.

Each request is a resident's own report of a condition, which complements the inspector
(violations) and court (litigation) views. For each building we (a) roll up an `sr311`
total + an `sr311_open` count (still-open requests) + latest `sr311_last` date, and
(b) append one `building_events` row per request (event_type="311", detail=complaint_type).

This dataset carries a computed 10-digit `bbl` field, which we prefer; when it's absent
we fall back to resolving `incident_address` through the address->BBL crosswalk
(`pricefixed/engine/crosswalk`), the same dogfooding path DOB complaints + evictions use.
The share resolved by each path is reported at the end. Verified keys (2026-07):
unique_key, bbl, incident_address, incident_zip, complaint_type, descriptor, status
(Open/Closed/Pending/...), agency, created_date (ISO like "2022-06-27T12:03:32.000")."""
import sqlite3

from ..core import fetch  # noqa: F401 — parity with adapter style
from .core import RecordSource, socrata, upsert_building, add_events
# bbl_for_address / build_crosswalk are imported lazily inside the methods below — a
# module-level import deadlocks the engine<->record circular import (see dob_complaints).

DATASET_ID = "erm2-nwe9"

# The housing-relevant slice: requests routed to HPD (the housing agency). Everything a
# tenant reports about their building — heat, hot water, plumbing, pests, mold — lands here.
HOUSING_WHERE = "agency='HPD'"


def iso_date(dt):
    """311 timestamps look like "2022-06-27T12:03:32.000" -> "2022-06-27"."""
    if not dt:
        return None
    return str(dt)[:10]


class ServiceRequests311Source(RecordSource):
    name = "sr311"
    description = "311 Service Requests (HPD housing slice) — complaint events + open/total counts"

    SELECT = "unique_key,bbl,incident_address,incident_zip,complaint_type,status,created_date"

    def _ensure_crosswalk(self, conn, zips):
        """Build crosswalk coverage (via PLUTO) for zips not already held, so the
        incident_address fallback is a genuine match rather than an empty-table miss."""
        from ..engine.crosswalk import build_crosswalk
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
        from ..engine.crosswalk import bbl_for_address
        rows = socrata(DATASET_ID, select=self.SELECT, where=HOUSING_WHERE,
                       order="created_date DESC", limit=limit)

        # Only build crosswalk for the zips of rows that actually LACK a bbl — most rows
        # carry one, so the fallback is a small, targeted top-up.
        no_bbl_zips = {r.get("incident_zip") for r in rows
                       if not (r.get("bbl") and str(r.get("bbl")).strip().isdigit())}
        self._ensure_crosswalk(conn, no_bbl_zips)

        events = []
        agg: dict[str, dict] = {}
        via_bbl = 0        # resolved by the dataset's own bbl
        via_crosswalk = 0  # resolved by the address fallback
        unresolved = 0     # no bbl and no crosswalk match
        for r in rows:
            raw = r.get("bbl")
            bbl = None
            if raw and str(raw).strip().isdigit() and len(str(raw).strip()) == 10:
                bbl = str(raw).strip()
                via_bbl += 1
            elif r.get("incident_address"):
                bbl = bbl_for_address(conn, r.get("incident_address"),
                                      zipcode=r.get("incident_zip"))
                if bbl:
                    via_crosswalk += 1
            if not bbl:
                unresolved += 1
                continue
            date = iso_date(r.get("created_date"))
            status = (r.get("status") or "").strip()
            events.append({
                "bbl": bbl, "event_type": "311", "event_date": date,
                "source": self.name, "party": status or None,
                "detail": r.get("complaint_type"),
            })
            a = agg.setdefault(bbl, {"count": 0, "open": 0, "last": None})
            a["count"] += 1
            if status.lower() == "open":
                a["open"] += 1
            if date and (a["last"] is None or date > a["last"]):
                a["last"] = date

        add_events(conn, events)
        for bbl, a in agg.items():
            upsert_building(conn, bbl, {
                "sr311": a["count"], "sr311_open": a["open"], "sr311_last": a["last"],
            })
        conn.commit()

        total = via_bbl + via_crosswalk + unresolved
        if total:
            print(f"  resolved {via_bbl + via_crosswalk}/{total}: "
                  f"{via_bbl} via dataset bbl, {via_crosswalk} via address crosswalk, "
                  f"{unresolved} unresolved")
        return len(events)
