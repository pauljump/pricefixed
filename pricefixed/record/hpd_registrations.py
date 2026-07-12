"""HPD Registrations (+ Contacts) — building ownership.

Multi-unit residential buildings must register annually with HPD. Dataset
`tesw-yqqr` gives one row per registered building (with block/lot but no owner name);
the companion Contacts dataset `feu5-w2e2` carries the owner name + business address,
joined on `registrationid`. We enrich each building's `owner_name` /
`owner_business_address`.

This registrations dataset has no BBL field, so we build it from boroid(1) + block(5)
+ lot(4). Verified keys (2026-07): registrations -> registrationid, boroid, block,
lot; contacts -> registrationid, type, corporationname, businesshousenumber,
businessstreetname, businessapartment, businesscity, businessstate, businesszip."""
from ..core import fetch  # noqa: F401 — parity with adapter style
from .core import RecordSource, socrata, upsert_building, boro_clause

REG_DATASET = "tesw-yqqr"
CONTACT_DATASET = "feu5-w2e2"

# Which contact best represents "the owner", most-authoritative first.
OWNER_TYPE_PRIORITY = ["HeadOfficer", "IndividualOwner", "CorporateOwner", "Owner", "Agent"]


def make_bbl(boroid, block, lot):
    """boroid(1) + block(5) + lot(4) -> the 10-digit BBL string."""
    try:
        return f"{int(boroid)}{int(block):05d}{int(lot):04d}"
    except (TypeError, ValueError):
        return None


def _business_address(c):
    line = " ".join(x for x in (c.get("businesshousenumber"), c.get("businessstreetname")) if x)
    apt = c.get("businessapartment")
    if apt:
        line = f"{line} #{apt}".strip()
    tail = " ".join(x for x in (c.get("businesscity"), c.get("businessstate"), c.get("businesszip")) if x)
    return ", ".join(x for x in (line.strip(), tail.strip()) if x) or None


def _owner_name(c):
    return c.get("corporationname") or " ".join(
        x for x in (c.get("firstname"), c.get("lastname")) if x
    ).strip() or None


def _pick_owner(contacts):
    """From all contacts for one registration, pick the best owner-ish one."""
    def rank(c):
        t = c.get("type") or ""
        return OWNER_TYPE_PRIORITY.index(t) if t in OWNER_TYPE_PRIORITY else len(OWNER_TYPE_PRIORITY)
    return sorted(contacts, key=rank)[0] if contacts else None


class HpdRegistrationsSource(RecordSource):
    name = "hpd_registrations"
    description = "HPD Registrations + Contacts — owner name & business address per BBL"

    REG_SELECT = "registrationid,boroid,block,lot"

    def pull(self, conn, limit=None, boro=None):
        # Registrations spells the borough as a numeric boroid ("1".."5"). Scope the
        # registrations pull server-side; contacts are then fetched by registrationid.
        where = boro_clause(boro, "boroid", "code")
        regs = socrata(REG_DATASET, select=self.REG_SELECT, where=where,
                       order="registrationid", limit=limit)
        # registrationid -> bbl, and the set of ids we need contacts for.
        reg_bbl: dict[str, str] = {}
        for r in regs:
            rid = r.get("registrationid")
            bbl = make_bbl(r.get("boroid"), r.get("block"), r.get("lot"))
            if rid and bbl:
                reg_bbl[rid] = bbl

        # Pull contacts for just those registrations, chunked to keep URLs sane.
        contacts_by_reg: dict[str, list] = {}
        ids = list(reg_bbl)
        for i in range(0, len(ids), 200):
            chunk = ids[i:i + 200]
            in_list = ",".join(f"'{x}'" for x in chunk)
            rows = socrata(CONTACT_DATASET, where=f"registrationid in ({in_list})")
            for c in rows:
                contacts_by_reg.setdefault(c.get("registrationid"), []).append(c)

        n = 0
        for rid, bbl in reg_bbl.items():
            owner = _pick_owner(contacts_by_reg.get(rid, []))
            if not owner:
                continue
            upsert_building(conn, bbl, {
                "owner_name": _owner_name(owner),
                "owner_business_address": _business_address(owner),
            })
            n += 1
        conn.commit()
        return n
