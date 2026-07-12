"""DOB Certificates of Occupancy — the legal-use history.

Dataset `bs8b-p36w` ("DOB Certificate Of Occupancy") on NYC Open Data: one row per C of O
the Department of Buildings issued — the document that says a building may legally be
occupied and for what (how many dwelling units, what use). A fresh C of O marks new
construction or a major conversion, so it's a clean public marker of when a building's
legal footprint changed. For each building we (a) roll up a `cofos` count + latest
`cofo_last` date onto its buildings row, and (b) append one `building_events` row per
certificate (event_type="cofo").

This dataset already carries a computed 10-digit `bbl` field; we prefer it and fall back
to building the BBL from borough(name)+block+lot. Verified keys (2026-07): bbl, borough
(full name), block, lot, c_o_issue_date (ISO like "2021-04-08T00:00:00.000"), issue_type
(Final/Temporary), job_type (A1/NB/...)."""
from ..core import fetch  # noqa: F401 — parity with adapter style
from .core import RecordSource, socrata, upsert_building, add_events, boro_clause

DATASET_ID = "bs8b-p36w"

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
    """DOB timestamps look like "2021-04-08T00:00:00.000" -> "2021-04-08"."""
    if not dt:
        return None
    return str(dt)[:10]


class CofoSource(RecordSource):
    name = "cofo"
    description = "DOB Certificates of Occupancy — C-of-O events + per-building counts"

    SELECT = "bbl,borough,block,lot,c_o_issue_date,issue_type,job_type"

    def pull(self, conn, limit=None, boro=None):
        # This dataset spells the borough as a full name ("BRONX"). Scope server-side.
        where = boro_clause(boro, "borough", "name")
        rows = socrata(DATASET_ID, select=self.SELECT, where=where,
                       order="c_o_issue_date DESC", limit=limit)
        events = []
        # Aggregate per building: total certificates seen this pull + latest date.
        agg: dict[str, dict] = {}
        for r in rows:
            bbl = make_bbl(r.get("bbl"), r.get("borough"), r.get("block"), r.get("lot"))
            if not bbl:
                continue
            date = iso_date(r.get("c_o_issue_date"))
            detail = " / ".join(x for x in (r.get("issue_type"), r.get("job_type")) if x) or None
            events.append({
                "bbl": bbl, "event_type": "cofo", "event_date": date,
                "source": self.name, "detail": detail,
            })
            a = agg.setdefault(bbl, {"count": 0, "last": None})
            a["count"] += 1
            if date and (a["last"] is None or date > a["last"]):
                a["last"] = date

        add_events(conn, events)
        for bbl, a in agg.items():
            upsert_building(conn, bbl, {"cofos": a["count"], "cofo_last": a["last"]})
        conn.commit()
        return len(events)
