"""HPD Housing Litigations — the tenant/HPD-vs-owner court history.

Dataset `59kj-x8nc` on NYC Open Data: one row per housing case brought in connection
with a building — a tenant action, an HPD heat/hot-water case, a comprehensive (7A)
proceeding, ... An open or judged litigation is a strong public signal that a building's
conditions escalated past inspection into court, and the walled listing sites never
show it. For each building we (a) roll up a `litigations` count + latest `litigation_last`
date onto its buildings row, and (b) append one `building_events` row per case
(event_type="litigation").

This dataset already carries a computed 10-digit `bbl` field; we prefer it and fall back
to building the BBL from boroid+block+lot. Verified keys (2026-07): litigationid, bbl,
boroid (numeric "1".."5"), block, lot, casetype (Heat and Hot Water / Tenant Action /
Comprehensive / ...), casestatus (OPEN/CLOSED), casejudgement (YES/NO), respondent,
caseopendate (ISO like "2023-04-20T00:00:00.000")."""
from ..core import fetch  # noqa: F401 — parity with adapter style
from .core import RecordSource, socrata, upsert_building, add_events

DATASET_ID = "59kj-x8nc"


def make_bbl(bbl, boroid, block, lot):
    """Prefer the dataset's own 10-digit bbl; else build boroid(1)+block(5)+lot(4)."""
    if bbl:
        s = str(bbl).strip()
        if s.isdigit() and len(s) == 10:
            return s
    try:
        code = int(boroid)
        if not 1 <= code <= 5:
            return None
        return f"{code}{int(block):05d}{int(lot):04d}"
    except (TypeError, ValueError):
        return None


def iso_date(dt):
    """HPD timestamps look like "2023-04-20T00:00:00.000" -> "2023-04-20"."""
    if not dt:
        return None
    return str(dt)[:10]


class HpdLitigationSource(RecordSource):
    name = "litigation"
    description = "HPD Housing Litigations — court-case events + per-building counts"

    SELECT = "bbl,boroid,block,lot,casetype,casestatus,caseopendate"

    def pull(self, conn, limit=None):
        rows = socrata(DATASET_ID, select=self.SELECT, order="caseopendate DESC", limit=limit)
        events = []
        # Aggregate per building: total cases seen this pull + latest date.
        agg: dict[str, dict] = {}
        for r in rows:
            bbl = make_bbl(r.get("bbl"), r.get("boroid"), r.get("block"), r.get("lot"))
            if not bbl:
                continue
            date = iso_date(r.get("caseopendate"))
            detail = " / ".join(x for x in (r.get("casetype"), r.get("casestatus")) if x) or None
            events.append({
                "bbl": bbl, "event_type": "litigation", "event_date": date,
                "source": self.name, "party": r.get("casestatus"), "detail": detail,
            })
            a = agg.setdefault(bbl, {"count": 0, "last": None})
            a["count"] += 1
            if date and (a["last"] is None or date > a["last"]):
                a["last"] = date

        add_events(conn, events)
        for bbl, a in agg.items():
            upsert_building(conn, bbl, {"litigations": a["count"], "litigation_last": a["last"]})
        conn.commit()
        return len(events)
