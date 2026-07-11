"""HPD Complaints — the tenant-complaint history.

Dataset `ygpa-z7cr` ("Housing Maintenance Code Complaints and Problems") on NYC Open
Data: one row per *problem* a tenant reported to HPD (a single complaint can carry
several problems). Where a violation is what an inspector *issued*, a complaint is what
a resident *reported* — the leading edge of the same signal. For each building we
(a) roll up a `complaints` count + latest `complaints_last` date onto its buildings row,
and (b) append one `building_events` row per problem (event_type="complaint").

This dataset already carries a computed 10-digit `bbl` field; we prefer it and fall back
to building the BBL from borough(name)+block+lot. Verified keys (2026-07): bbl, borough
(full name), block, lot, received_date (ISO like "2026-07-11T00:04:10.000"),
major_category / minor_category / problem_code (the condition), complaint_status."""
from ..core import fetch  # noqa: F401 — parity with adapter style
from .core import RecordSource, socrata, upsert_building, add_events

DATASET_ID = "ygpa-z7cr"

BORO_CODE = {"MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4", "STATEN ISLAND": "5"}


def make_bbl(bbl, borough, block, lot):
    """Prefer the dataset's own 10-digit bbl; else build boro-code(1)+block(5)+lot(4)."""
    if bbl:
        s = str(bbl).strip()
        if s.isdigit() and len(s) == 10:
            return s
    code = BORO_CODE.get((borough or "").strip().upper())
    if not code:
        return None
    try:
        return f"{code}{int(block):05d}{int(lot):04d}"
    except (TypeError, ValueError):
        return None


def iso_date(dt):
    """HPD timestamps look like "2026-07-11T00:04:10.000" -> "2026-07-11"."""
    if not dt:
        return None
    return str(dt)[:10]


class HpdComplaintsSource(RecordSource):
    name = "hpd_complaints"
    description = "HPD Complaints — tenant-reported problem events + per-building counts"

    SELECT = "bbl,borough,block,lot,received_date,major_category,minor_category,problem_code,complaint_status"

    def pull(self, conn, limit=None):
        rows = socrata(DATASET_ID, select=self.SELECT, order="received_date DESC", limit=limit)
        events = []
        # Aggregate per building: total complaints seen this pull + latest date.
        agg: dict[str, dict] = {}
        for r in rows:
            bbl = make_bbl(r.get("bbl"), r.get("borough"), r.get("block"), r.get("lot"))
            if not bbl:
                continue
            date = iso_date(r.get("received_date"))
            detail = " / ".join(
                x for x in (r.get("major_category"), r.get("minor_category"), r.get("problem_code")) if x
            ) or None
            events.append({
                "bbl": bbl, "event_type": "complaint", "event_date": date,
                "source": self.name, "party": r.get("complaint_status"), "detail": detail,
            })
            a = agg.setdefault(bbl, {"count": 0, "last": None})
            a["count"] += 1
            if date and (a["last"] is None or date > a["last"]):
                a["last"] = date

        add_events(conn, events)
        for bbl, a in agg.items():
            upsert_building(conn, bbl, {"complaints": a["count"], "complaints_last": a["last"]})
        conn.commit()
        return len(events)
