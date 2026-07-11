"""HPD Housing Maintenance Code Violations — the enforcement history.

Dataset `wvxf-dwi5` on NYC Open Data: one row per violation an HPD inspector issued
against a residential building for a Housing Maintenance Code condition (no heat, lead,
vermin, ...). This is the highest-value record layer — a building's open violations are
the clearest public signal of how it's actually run, and the walled listing sites never
show them. For each building we (a) roll up a `violations` count + latest `viol_last`
date onto its buildings row, and (b) append one `building_events` row per violation
(event_type="violation").

This dataset has no BBL field, so we build it: boroid(1) + block(5, zero-padded) +
lot(4, zero-padded). Verified keys (2026-07): boroid (numeric "1".."5"), block, lot,
class (violation hazard class A/B/C/I), novdescription (the notice-of-violation text),
novissueddate + inspectiondate (ISO like "2011-07-21T00:00:00.000"), violationstatus
(Open/Close). novissueddate is frequently null on older rows, so we order by — and fall
back to — inspectiondate for the event date."""
from ..core import fetch  # noqa: F401 — parity with adapter style
from .core import RecordSource, socrata, upsert_building, add_events

DATASET_ID = "wvxf-dwi5"

# Cap the notice text so a single verbose violation doesn't bloat the events table.
DETAIL_MAX = 300


def make_bbl(boroid, block, lot):
    """boroid(1) + block(5) + lot(4) -> the 10-digit BBL string."""
    try:
        code = int(boroid)
        if not 1 <= code <= 5:
            return None
        return f"{code}{int(block):05d}{int(lot):04d}"
    except (TypeError, ValueError):
        return None


def iso_date(dt):
    """HPD timestamps look like "2011-07-21T00:00:00.000" -> "2011-07-21"."""
    if not dt:
        return None
    return str(dt)[:10]


class HpdViolationsSource(RecordSource):
    name = "hpd_violations"
    description = "HPD Housing Maintenance Code Violations — violation events + per-building counts"

    SELECT = "boroid,block,lot,class,novdescription,novissueddate,inspectiondate,violationstatus"

    def pull(self, conn, limit=None):
        rows = socrata(DATASET_ID, select=self.SELECT, order="inspectiondate DESC", limit=limit)
        events = []
        # Aggregate per building: total violations seen this pull + latest date.
        agg: dict[str, dict] = {}
        for r in rows:
            bbl = make_bbl(r.get("boroid"), r.get("block"), r.get("lot"))
            if not bbl:
                continue
            date = iso_date(r.get("novissueddate") or r.get("inspectiondate"))
            cls = r.get("class")
            desc = (r.get("novdescription") or "").strip()
            detail = " ".join(p for p in (f"Class {cls}" if cls else "", desc) if p).strip() or None
            if detail and len(detail) > DETAIL_MAX:
                detail = detail[:DETAIL_MAX].rstrip() + "…"
            events.append({
                "bbl": bbl, "event_type": "violation", "event_date": date,
                "source": self.name, "party": r.get("violationstatus"), "detail": detail,
            })
            a = agg.setdefault(bbl, {"count": 0, "last": None})
            a["count"] += 1
            if date and (a["last"] is None or date > a["last"]):
                a["last"] = date

        add_events(conn, events)
        for bbl, a in agg.items():
            upsert_building(conn, bbl, {"violations": a["count"], "viol_last": a["last"]})
        conn.commit()
        return len(events)
