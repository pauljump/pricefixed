"""DOB Complaints Received — the buildings-department complaint history.

Dataset `eabe-havv` on NYC Open Data: one row per complaint the Department of Buildings
received (illegal work, structural, no permit, ...). Unlike the HPD feeds this dataset is
keyed by BIN + house-number/street with NO BBL and no borough/block/lot — so it's the
natural place to *dogfood our own address->BBL crosswalk* (`pricefixed/engine/crosswalk`).
We resolve each complaint's address through the crosswalk and skip rows that don't match
(the resolve rate is reported at the end of the pull). For each resolved building we
(a) roll up a `dob_complaints` count + latest `dob_complaints_last` date, and (b) append
one `building_events` row per complaint (event_type="dob_complaint").

Verified keys (2026-07): bin, house_number, house_street, zip_code, complaint_category
(numeric code), complaint_number, status (ACTIVE/CLOSED), date_entered (MM/DD/YYYY),
disposition_code, inspection_date."""
import sqlite3

from ..core import fetch  # noqa: F401 — parity with adapter style
from .core import RecordSource, socrata, upsert_building, add_events
# NOTE: bbl_for_address / build_crosswalk are imported lazily inside the methods that
# use them. A module-level import here would deadlock: engine/__init__ eagerly imports
# crosswalk, which imports record.core, which runs record/__init__, which imports this
# module — pulling engine.crosswalk back before it has finished defining those names.

DATASET_ID = "eabe-havv"


def iso_date(mmddyyyy):
    """DOB complaints store date_entered as MM/DD/YYYY -> YYYY-MM-DD (sortable)."""
    if not mmddyyyy:
        return None
    parts = str(mmddyyyy).split("/")
    if len(parts) == 3:
        m, d, y = parts
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return str(mmddyyyy)[:10]


class DobComplaintsSource(RecordSource):
    name = "dob_complaints"
    description = "DOB Complaints Received — address-resolved complaint events + per-building counts"

    SELECT = "bin,house_number,house_street,zip_code,complaint_category,complaint_number,status,date_entered"

    def _ensure_crosswalk(self, conn, zips):
        """Make sure the crosswalk covers the zips in this sample so resolution is real.

        The crosswalk table lives in the same db; a fresh clone starts empty. We build
        (via PLUTO) only the zips we don't already hold — one scoped SoQL query, the same
        zip-scoped pattern the engine's demo uses — so the resolve rate reflects a genuine
        address->BBL match, not an empty table."""
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
        rows = socrata(DATASET_ID, select=self.SELECT, order="date_entered DESC", limit=limit)
        self._ensure_crosswalk(conn, {r.get("zip_code") for r in rows})

        events = []
        agg: dict[str, dict] = {}
        attempted = 0   # rows with a usable address string
        resolved = 0    # rows the crosswalk turned into a BBL
        for r in rows:
            house, street = r.get("house_number"), r.get("house_street")
            if not (house and street):
                continue
            attempted += 1
            address = f"{house} {street}"
            bbl = bbl_for_address(conn, address, zipcode=r.get("zip_code"))
            if not bbl:
                continue
            resolved += 1
            date = iso_date(r.get("date_entered"))
            detail = " / ".join(
                x for x in (
                    f"category {r.get('complaint_category')}" if r.get("complaint_category") else None,
                    r.get("status"),
                ) if x
            ) or None
            events.append({
                "bbl": bbl, "event_type": "dob_complaint", "event_date": date,
                "source": self.name, "party": r.get("status"), "detail": detail,
            })
            a = agg.setdefault(bbl, {"count": 0, "last": None})
            a["count"] += 1
            if date and (a["last"] is None or date > a["last"]):
                a["last"] = date

        add_events(conn, events)
        for bbl, a in agg.items():
            upsert_building(conn, bbl, {"dob_complaints": a["count"], "dob_complaints_last": a["last"]})
        conn.commit()

        rate = (100 * resolved / attempted) if attempted else 0.0
        print(f"  address->BBL crosswalk resolve rate: {resolved}/{attempted} = {rate:.0f}%")
        return len(events)
