"""DOB Permit Issuance — the permit history.

Dataset `ipu4-2q9a` on NYC Open Data: one row per permit issued. For each building
we (a) roll up a `permits` count + latest `permit_last` date onto its buildings row,
and (b) append one `building_events` row per permit (event_type="permit").

This dataset has no BBL field, so we build it: borough-code(1) + block(5, zero-padded)
+ lot(4, zero-padded). Verified keys (2026-07): borough (full name), block, lot,
issuance_date (MM/DD/YYYY), job_type, permit_type, work_type."""
from ..core import fetch  # noqa: F401 — parity with adapter style
from .core import RecordSource, socrata, upsert_building, add_events

DATASET_ID = "ipu4-2q9a"

BORO_CODE = {"MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4", "STATEN ISLAND": "5"}


def make_bbl(borough, block, lot):
    """borough-code(1) + block(5) + lot(4) -> the 10-digit BBL string."""
    code = BORO_CODE.get((borough or "").strip().upper())
    if not code:
        return None
    try:
        return f"{code}{int(block):05d}{int(lot):04d}"
    except (TypeError, ValueError):
        return None


def iso_date(mmddyyyy):
    """MM/DD/YYYY -> YYYY-MM-DD (sortable). Returns the raw value if it can't parse."""
    if not mmddyyyy:
        return None
    parts = mmddyyyy.split("/")
    if len(parts) == 3:
        m, d, y = parts
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return mmddyyyy[:10]


class DobPermitsSource(RecordSource):
    name = "dob_permits"
    description = "DOB Permit Issuance — permit events + per-building permit counts"

    SELECT = "borough,block,lot,issuance_date,filing_date,job_type,permit_type,work_type"

    def pull(self, conn, limit=None):
        rows = socrata(DATASET_ID, select=self.SELECT, order="issuance_date DESC", limit=limit)
        events = []
        # Aggregate per building: total permits seen this pull + latest date.
        agg: dict[str, dict] = {}
        for r in rows:
            bbl = make_bbl(r.get("borough"), r.get("block"), r.get("lot"))
            if not bbl:
                continue
            date = iso_date(r.get("issuance_date") or r.get("filing_date"))
            detail = " / ".join(x for x in (r.get("job_type"), r.get("permit_type"), r.get("work_type")) if x) or None
            events.append({
                "bbl": bbl, "event_type": "permit", "event_date": date,
                "source": self.name, "detail": detail,
            })
            a = agg.setdefault(bbl, {"count": 0, "last": None})
            a["count"] += 1
            if date and (a["last"] is None or date > a["last"]):
                a["last"] = date

        add_events(conn, events)
        for bbl, a in agg.items():
            upsert_building(conn, bbl, {"permits": a["count"], "permit_last": a["last"]})
        conn.commit()
        return len(events)
