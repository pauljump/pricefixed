"""ACRIS property sales — the sale-history half of the building record.

ACRIS (the City Register's recording system) is split across two Socrata datasets
joined on `document_id`:
  - Real Property Master `bnx9-e6tj` — one row per recorded document: doc_type,
    document_amt (sale price), document_date + recorded_datetime.
  - Real Property Legals `8h5j-fqxa` — the property(ies) each document touches:
    borough (numeric code 1-5), block, lot (+ unit for condos), property_type.

For each recorded *sale* deed we (a) append one `building_events` row
(event_type="sale", amount=document_amt, detail=doc_type) and (b) roll up a `sales`
count + latest `sales_last` date onto the building's spine row.

Deeds have no BBL field, so we build it from the Legals row:
borough-code(1) + block(5, zero-padded) + lot(4, zero-padded).

Verified keys (2026-07): master -> document_id, doc_type, document_amt,
document_date, recorded_datetime (all ISO like "2026-06-03T00:00:00.000");
legals -> document_id, borough (numeric "1".."5"), block, lot, unit, property_type.
Verified sale doc_types present: DEED (3.6M), DEEDO (30k) are the arm's-length sale
deeds; the rest (DEED COR / DEED, LE / DEED, TS ...) are corrections/life-estates/etc.
"""
from ..core import fetch  # noqa: F401 — parity with adapter style
from .core import RecordSource, socrata, upsert_building, add_events

MASTER_DATASET = "bnx9-e6tj"
LEGALS_DATASET = "8h5j-fqxa"

# Which ACRIS doc_types count as a property *sale*. DEED and DEEDO are the
# arm's-length conveyances; correction/life-estate/timeshare deeds are excluded.
SALE_DOC_TYPES = ["DEED", "DEEDO"]


def make_bbl(borough, block, lot):
    """borough-code(1) + block(5) + lot(4) -> the 10-digit BBL string.

    ACRIS Legals already stores borough as the numeric code ("1".."5")."""
    try:
        code = int(borough)
        if not 1 <= code <= 5:
            return None
        return f"{code}{int(block):05d}{int(lot):04d}"
    except (TypeError, ValueError):
        return None


def iso_date(dt):
    """ACRIS timestamps look like "2026-06-03T00:00:00.000" -> "2026-06-03"."""
    if not dt:
        return None
    return str(dt)[:10]


def _amount(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


class AcrisSalesSource(RecordSource):
    name = "acris_sales"
    description = ("ACRIS property sales — recorded deeds/sales as building_events "
                  "+ per-building sale counts")

    MASTER_SELECT = "document_id,doc_type,document_amt,document_date,recorded_datetime"
    LEGALS_SELECT = "document_id,borough,block,lot,unit,property_type"

    def pull(self, conn, limit=None):
        # 1. Pull the most recent sale deeds from Master (filtered to sale doc_types).
        in_types = ",".join(f"'{t}'" for t in SALE_DOC_TYPES)
        masters = socrata(
            MASTER_DATASET,
            select=self.MASTER_SELECT,
            where=f"doc_type in ({in_types})",
            order="recorded_datetime DESC",
            limit=limit,
        )
        # document_id -> {amount, date, doc_type}
        deals: dict[str, dict] = {}
        for m in masters:
            did = m.get("document_id")
            if not did:
                continue
            deals[did] = {
                "doc_type": m.get("doc_type"),
                "amount": _amount(m.get("document_amt")),
                "date": iso_date(m.get("recorded_datetime") or m.get("document_date")),
            }

        # 2. Pull the matching Legals rows (which lot(s) each deed touches), chunked.
        legals_by_doc: dict[str, list] = {}
        ids = list(deals)
        for i in range(0, len(ids), 200):
            chunk = ids[i:i + 200]
            in_ids = ",".join(f"'{x}'" for x in chunk)
            rows = socrata(LEGALS_DATASET, select=self.LEGALS_SELECT,
                           where=f"document_id in ({in_ids})")
            for r in rows:
                legals_by_doc.setdefault(r.get("document_id"), []).append(r)

        # 3. Join: one sale event per (deed x property lot). Roll up per building.
        events = []
        agg: dict[str, dict] = {}
        for did, deal in deals.items():
            for leg in legals_by_doc.get(did, []):
                bbl = make_bbl(leg.get("borough"), leg.get("block"), leg.get("lot"))
                if not bbl:
                    continue
                date = deal["date"]
                events.append({
                    "bbl": bbl, "event_type": "sale", "event_date": date,
                    "source": self.name, "amount": deal["amount"],
                    "detail": deal["doc_type"],
                })
                a = agg.setdefault(bbl, {"count": 0, "last": None})
                a["count"] += 1
                if date and (a["last"] is None or date > a["last"]):
                    a["last"] = date

        add_events(conn, events)
        for bbl, a in agg.items():
            upsert_building(conn, bbl, {"sales": a["count"], "sales_last": a["last"]})
        conn.commit()
        return len(events)
