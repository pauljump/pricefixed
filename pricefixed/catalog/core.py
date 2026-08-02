"""The canonical catalog layer for pricefixed.

The scraper and public-record databases remain source stores: they preserve what a
publisher or public agency said. This module builds a third database which resolves
only well-supported claims into a stable NYC housing hierarchy:

    BBL -> building -> address -> unit -> observations

It intentionally favors unresolved observations over a bad merge. A listing whose
address maps to zero or multiple BBLs, or whose unit label is absent, is still kept
with its source evidence but does not become a canonical unit.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from ..engine.crosswalk import build_crosswalk_pad, normalize_address
from ..engine.dedupe import normalize_unit
from ..record.core import BOROUGHS, boro_clause, socrata
from ..record.violations import iso_date, make_bbl
from .xlsx import read_xlsx_rows

HPD_VIOLATIONS_DATASET = "wvxf-dwi5"
HPD_VIOLATIONS_SELECT = (
    "violationid,boroid,block,lot,apartment,housenumber,streetname,zip,"
    "class,novdescription,novissueddate,inspectiondate,violationstatus"
)
HPD_PROBLEMS_DATASET = "ygpa-z7cr"
HPD_PROBLEMS_SELECT = (
    "problem_id,complaint_id,unique_key,received_date,borough,house_number,street_name,post_code,"
    "block,lot,apartment,problem_status,complaint_status,bbl,bin,unit_type,space_type"
)
NYCHA_HMC_VIOLATIONS_DATASET = "im9z-53hg"
NYCHA_HMC_VIOLATIONS_SELECT = (
    "viol_seq_no,bldg_id,boro,phn,str_nm,zip,development_name,tds_no,stairhall_no,"
    "actl_unit_insp,actl_stry,blk,lot,viol_desc,hzrd_clas,insp_dt,viol_appr_dt,"
    "issued_in_err,bin,bbl"
)
HPD_OMO_WORK_ORDERS_DATASET = "mdbu-nrqn"
HPD_OMO_WORK_ORDERS_SELECT = (
    "omoid,omonumber,boro_id,block,lot,bbl,apartment,housenumber,streetname,zip,"
    "omocreatedate,omoawarddate,lifecycle,worktypegeneral,omostatusreason,omodescription"
)
ACRIS_PROPERTY_LEGALS_DATASET = "8h5j-fqxa"
ACRIS_PROPERTY_LEGALS_SELECT = (
    "document_id,borough,block,lot,property_type,street_number,street_name,unit,good_through_date"
)
ANNUALIZED_SALES_DATASET = "w2pb-icbu"
ANNUALIZED_SALES_SELECT = (
    "borough,block,lot,bbl,address,apartment_number,zip_code,sale_price,sale_date,"
    "building_class_category,building_class_at_time_of,residential_units,total_units"
)
ROLLING_SALES_DATASET = "usep-8jbt"
ROLLING_SALES_SELECT = (
    "borough,block,lot,address,apartment_number,zip_code,sale_price,sale_date,"
    "building_class_category,building_class_at_time_of,residential_units,total_units"
)
EVICTIONS_DATASET = "6z8x-wfk4"
EVICTIONS_SELECT = (
    "court_index_number,docket_number,eviction_address,eviction_apt_num,executed_date,"
    "residential_commercial_ind,borough,eviction_zip,ejectment,eviction_possession,bin,bbl"
)
DOB_NOW_JOBS_DATASET = "w9ak-ipjd"
DOB_NOW_JOBS_SELECT = (
    "job_filing_number,filing_status,house_no,street_name,borough,block,lot,bbl,bin,"
    "work_on_floor,apt_condo_no_s,filing_date,current_status_date,approved_date,signoff_date,"
    "job_type,job_description,existing_dwelling_units,proposed_dwelling_units,postcode"
)
DOB_NOW_PERMITS_DATASET = "rbx6-tga4"
DOB_NOW_PERMITS_SELECT = (
    "job_filing_number,work_permit,filing_reason,house_no,street_name,borough,block,lot,bbl,bin,"
    "work_on_floor,apt_condo_no_s,approved_date,issued_date,expired_date,permit_status,"
    "work_type,job_description,zip_code"
)
DOB_NOW_CERTIFICATES_DATASET = "pkdm-hqz6"
DOB_NOW_CERTIFICATES_SELECT = (
    "job_filing_name,job_type,bin,borough,house_no,street_name,block,lot,zip_code,"
    "submitted_date,c_of_o_status,c_of_o_sequence,c_of_o_filing_type,c_of_o_issuance_date,"
    "application_number,number_of_dwelling_units,c_of_o_number,bbl"
)
HPD_REGISTRATIONS_DATASET = "tesw-yqqr"
HPD_REGISTRATIONS_SELECT = (
    "registrationid,buildingid,boroid,boro,housenumber,streetname,zip,block,lot,bin,"
    "lastregistrationdate,registrationenddate"
)
CONDO_UNITS_DATASET = "eguu-7ie3"
CONDO_UNITS_SELECT = (
    "condo_base_bbl,condo_number,condo_key,condo_base_bbl_key,unit_bbl,"
    "unit_designation,floor_text,model,geometry_type,effective_tax_year"
)

# NYC's 2023 housing-stock benchmark used for coverage reporting. This is a
# denominator only: it never creates or names a canonical unit.
NYC_HOUSING_STOCK_TARGET = 3_705_000

# These are HPD location descriptions, not apartment labels. A direct BBL is not
# enough to create a dwelling unit when the agency record names a common area.
NON_DWELLING_UNIT_LABELS = {
    "BASEMENT", "CELLAR", "ROOF", "PUBLIC HALL", "PUBLIC AREA", "HALLWAY",
    "STAIRWAY", "STAIRWELL", "ELEVATOR", "ENTIRE BUILDING", "BUILDING WIDE",
    "BLDG", "BUILDING", "MEDICAL", "COMMERCIAL", "RETAIL", "OFFICE", "PARKING", "STORAGE", "RESIDENTIAL",
}

# The archived Vayo all-NYC-unit export contains a small number of scraper
# artifacts in its otherwise unit-bearing rows. They are retained nowhere as
# apartments; the raw archive remains the source of record for audit purposes.
VAYO_NON_UNIT_LABELS = {"FINISHES", "MANAGEMENT"}

# DOF documents that co-op sales may put the apartment after a comma in the
# address while leaving apartment_number empty. Only accept compact labels with
# a digit (or a small set of explicit non-numeric labels); never parse a freeform
# address tail into a unit.
_DOF_ADDRESS_UNIT = re.compile(r"^(?:[A-Z]?\d[A-Z0-9]{0,6}|\d{1,4}[A-Z]{0,4}|PH|PENTHOUSE)$")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _id(prefix, *parts):
    material = "\\x1f".join("" if p is None else str(p) for p in parts)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:20]}"


def _normalize_bbl(raw):
    """Normalize a numeric NYC BBL to its 10-digit text representation."""
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    return f"{value:010d}" if 1_000_000_000 <= value <= 5_999_999_999 else None


def init_catalog_db(path):
    """Open a catalog database, creating the evidence and entity schema if needed."""
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(
        """
        -- A publisher or agency and the method used to obtain its public material.
        CREATE TABLE IF NOT EXISTS sources (
            source          TEXT PRIMARY KEY,
            source_kind     TEXT NOT NULL,
            methodology     TEXT NOT NULL,
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL
        );

        -- The retrieved primary material. payload is the unmodified payload supplied
        -- by the upstream store; it is never replaced by a normalized representation.
        CREATE TABLE IF NOT EXISTS source_documents (
            document_id     TEXT PRIMARY KEY,
            source          TEXT NOT NULL,
            source_ref      TEXT NOT NULL,
            retrieved_at    TEXT NOT NULL,
            payload          TEXT,
            payload_kind     TEXT NOT NULL,
            UNIQUE(source, source_ref, retrieved_at)
        );
        CREATE INDEX IF NOT EXISTS idx_documents_source ON source_documents(source, source_ref);

        -- Official geography. BBL is the canonical public identifier for a tax lot.
        CREATE TABLE IF NOT EXISTS buildings (
            bbl             TEXT PRIMARY KEY,
            borough         TEXT,
            primary_address TEXT,
            zipcode         TEXT,
            units_res       INTEGER,
            units_total     INTEGER,
            building_class  TEXT,
            source          TEXT NOT NULL,
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS addresses (
            address_id      TEXT PRIMARY KEY,
            bbl             TEXT NOT NULL,
            address         TEXT NOT NULL,
            normalized      TEXT NOT NULL,
            zipcode         TEXT,
            source          TEXT NOT NULL,
            UNIQUE(bbl, normalized)
        );
        CREATE INDEX IF NOT EXISTS idx_addresses_normalized ON addresses(normalized);

        -- A canonical unit exists only after a high-confidence BBL + unit-label join.
        CREATE TABLE IF NOT EXISTS units (
            unit_id         TEXT PRIMARY KEY,
            bbl             TEXT NOT NULL,
            unit_label      TEXT NOT NULL,
            normalized_unit TEXT NOT NULL,
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL,
            UNIQUE(bbl, normalized_unit)
        );
        CREATE INDEX IF NOT EXISTS idx_units_bbl ON units(bbl);

        -- A tax lot may contain several addressable buildings. Keep a source-derived
        -- premise layer so identical labels at different street addresses (for
        -- example, Peter Cooper Road) are never collapsed into one apartment.
        CREATE TABLE IF NOT EXISTS premises (
            premise_id      TEXT PRIMARY KEY,
            bbl             TEXT NOT NULL,
            address         TEXT NOT NULL,
            normalized      TEXT NOT NULL,
            zipcode         TEXT,
            source          TEXT NOT NULL,
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL,
            UNIQUE(bbl, normalized)
        );
        CREATE INDEX IF NOT EXISTS idx_premises_bbl ON premises(bbl);
        CREATE TABLE IF NOT EXISTS addressable_units (
            addressable_unit_id TEXT PRIMARY KEY,
            premise_id      TEXT NOT NULL,
            unit_label      TEXT NOT NULL,
            normalized_unit TEXT NOT NULL,
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL,
            UNIQUE(premise_id, normalized_unit)
        );
        CREATE INDEX IF NOT EXISTS idx_addressable_units_premise ON addressable_units(premise_id);
        CREATE TABLE IF NOT EXISTS addressable_unit_progress (
            source          TEXT PRIMARY KEY,
            cursor_rowid    INTEGER NOT NULL,
            updated_at      TEXT NOT NULL
        );

        -- Keyset state for immutable local/archive source imports. The cursor is
        -- advanced only in the same committed catalog transaction as its rows.
        CREATE TABLE IF NOT EXISTS archive_import_progress (
            source          TEXT PRIMARY KEY,
            cursor_ref      TEXT,
            updated_at      TEXT NOT NULL
        );

        -- A condominium tax lot is an official legal/property identity. It is not
        -- assumed to be the apartment label used by a resident or rental listing.
        CREATE TABLE IF NOT EXISTS official_unit_lots (
            unit_lot_bbl       TEXT PRIMARY KEY,
            condo_base_bbl     TEXT,
            condo_number       TEXT,
            condo_key          TEXT,
            condo_base_bbl_key TEXT,
            unit_designation   TEXT,
            floor_text         TEXT,
            model              TEXT,
            geometry_type      TEXT,
            effective_tax_year TEXT,
            source             TEXT NOT NULL,
            source_ref         TEXT NOT NULL,
            document_id        TEXT NOT NULL,
            record_status      TEXT NOT NULL,
            first_seen         TEXT NOT NULL,
            last_seen          TEXT NOT NULL,
            raw_fields         TEXT NOT NULL,
            UNIQUE(source, source_ref)
        );
        CREATE INDEX IF NOT EXISTS idx_official_unit_lots_base ON official_unit_lots(condo_base_bbl);

        -- Future evidence may relate a tax lot to a resident-facing physical unit.
        -- Leaving the initial links unresolved is intentional: a shared designation
        -- like "4B" is not sufficient proof by itself.
        CREATE TABLE IF NOT EXISTS official_unit_lot_links (
            unit_lot_bbl       TEXT PRIMARY KEY,
            unit_id            TEXT,
            status             TEXT NOT NULL,
            confidence         REAL,
            method             TEXT NOT NULL,
            rationale          TEXT NOT NULL,
            linked_at          TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_unit_lot_links_unit ON official_unit_lot_links(unit_id);

        -- An observation is a claim made by one source at one time. Price history is
        -- not collapsed: it remains a sequence of source-attributed observations.
        CREATE TABLE IF NOT EXISTS observations (
            observation_id  TEXT PRIMARY KEY,
            document_id     TEXT,
            source          TEXT NOT NULL,
            source_ref      TEXT NOT NULL,
            observed_at     TEXT NOT NULL,
            observation_kind TEXT NOT NULL,
            address         TEXT,
            unit_label      TEXT,
            bedrooms        REAL,
            bathrooms       REAL,
            price           REAL,
            status          TEXT,
            raw_fields      TEXT,
            evidence_grade  TEXT NOT NULL,
            UNIQUE(source, source_ref, observed_at, observation_kind)
        );
        CREATE INDEX IF NOT EXISTS idx_observations_source_ref ON observations(source, source_ref);
        CREATE INDEX IF NOT EXISTS idx_observations_observed ON observations(observed_at);

        -- Resolution is a claim of our own, distinct from source material. It carries
        -- the method and confidence so consumers can decide whether to trust it.
        CREATE TABLE IF NOT EXISTS entity_matches (
            observation_id  TEXT NOT NULL,
            entity_type     TEXT NOT NULL,
            entity_id       TEXT,
            status          TEXT NOT NULL,
            confidence      REAL,
            method          TEXT NOT NULL,
            rationale       TEXT NOT NULL,
            matched_at      TEXT NOT NULL,
            PRIMARY KEY (observation_id, entity_type)
        );
        CREATE INDEX IF NOT EXISTS idx_matches_entity ON entity_matches(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_matches_observation ON entity_matches(observation_id);
        CREATE INDEX IF NOT EXISTS idx_matches_type_status ON entity_matches(entity_type, status);

        -- An ambiguous address can legitimately point to several tax lots. Preserve
        -- those candidate BBLs for later evidence-based resolution instead of picking
        -- one opportunistically or throwing the ambiguity away.
        CREATE TABLE IF NOT EXISTS entity_match_candidates (
            observation_id  TEXT NOT NULL,
            entity_type     TEXT NOT NULL,
            candidate_id    TEXT NOT NULL,
            method          TEXT NOT NULL,
            rationale       TEXT NOT NULL,
            PRIMARY KEY (observation_id, entity_type, candidate_id)
        );
        CREATE INDEX IF NOT EXISTS idx_match_candidates_entity
            ON entity_match_candidates(entity_type, candidate_id);

        -- Resolution evidence is stored explicitly so a later reviewer can inspect
        -- the primary-source observations that justified an inferred candidate pick.
        CREATE TABLE IF NOT EXISTS entity_match_evidence (
            observation_id          TEXT NOT NULL,
            entity_type             TEXT NOT NULL,
            evidence_observation_id TEXT NOT NULL,
            role                    TEXT NOT NULL,
            PRIMARY KEY (observation_id, entity_type, evidence_observation_id)
        );
        CREATE INDEX IF NOT EXISTS idx_match_evidence_evidence
            ON entity_match_evidence(evidence_observation_id);

        -- Coverage snapshots describe the evidence universe at a moment in time.
        -- They never declare a building or its units complete.
        CREATE TABLE IF NOT EXISTS coverage_runs (
            run_id          TEXT PRIMARY KEY,
            scope           TEXT NOT NULL,
            as_of_date      TEXT NOT NULL,
            status           TEXT NOT NULL,
            hpd_rows         INTEGER NOT NULL,
            started_at       TEXT NOT NULL,
            completed_at     TEXT
        );
        CREATE TABLE IF NOT EXISTS coverage_hpd_registrations (
            run_id                  TEXT NOT NULL,
            registration_id         TEXT NOT NULL,
            bbl                     TEXT,
            hpd_building_id         TEXT,
            address                 TEXT,
            zipcode                 TEXT,
            registration_end_date   TEXT,
            timing_status           TEXT NOT NULL,
            document_id             TEXT NOT NULL,
            raw_fields              TEXT NOT NULL,
            PRIMARY KEY (run_id, registration_id)
        );
        CREATE TABLE IF NOT EXISTS building_coverage (
            run_id                  TEXT NOT NULL,
            bbl                     TEXT NOT NULL,
            membership_status       TEXT NOT NULL,
            pluto_units_res         INTEGER,
            canonical_unit_labels   INTEGER NOT NULL,
            official_unit_labels    INTEGER NOT NULL,
            listing_unit_labels     INTEGER NOT NULL,
            PRIMARY KEY (run_id, bbl)
        );

        -- A bulk-source page is a durable acquisition checkpoint. Rows themselves
        -- retain source provenance; this table makes an interrupted citywide run
        -- resumable without guessing which offsets were already committed.
        CREATE TABLE IF NOT EXISTS acquisition_pages (
            source              TEXT NOT NULL,
            scope               TEXT NOT NULL,
            offset              INTEGER NOT NULL,
            requested_rows      INTEGER NOT NULL,
            returned_rows       INTEGER NOT NULL,
            canonical_units_before INTEGER NOT NULL,
            canonical_units_after  INTEGER NOT NULL,
            started_at          TEXT NOT NULL,
            completed_at        TEXT NOT NULL,
            PRIMARY KEY (source, scope, offset)
        );
        CREATE TABLE IF NOT EXISTS acquisition_keysets (
            source              TEXT NOT NULL,
            scope               TEXT NOT NULL,
            cursor_date         TEXT,
            cursor_ref          TEXT,
            returned_rows       INTEGER NOT NULL,
            completed_at        TEXT NOT NULL,
            PRIMARY KEY (source, scope)
        );
        CREATE TABLE IF NOT EXISTS capacity_slot_runs (
            run_id              TEXT PRIMARY KEY,
            source              TEXT NOT NULL,
            source_document_id  TEXT NOT NULL,
            slot_count           INTEGER NOT NULL,
            generated_at         TEXT NOT NULL
        );
        -- A capacity slot is an anonymous position in a source-reported unit count.
        -- It is deliberately not a canonical apartment identity or unit label.
        CREATE TABLE IF NOT EXISTS housing_capacity_slots (
            slot_id             TEXT PRIMARY KEY,
            bbl                 TEXT NOT NULL,
            slot_ordinal        INTEGER NOT NULL,
            run_id              TEXT NOT NULL,
            UNIQUE(bbl, slot_ordinal)
        );
        CREATE INDEX IF NOT EXISTS idx_capacity_slots_bbl ON housing_capacity_slots(bbl);
        CREATE TABLE IF NOT EXISTS capacity_slot_progress (
            source              TEXT PRIMARY KEY,
            run_id              TEXT NOT NULL,
            cursor_bbl          TEXT,
            completed           INTEGER NOT NULL DEFAULT 0,
            updated_at          TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


class Catalog:
    """Build a canonical catalog from existing pricefixed SQLite source stores."""

    def __init__(self, conn):
        self.conn = conn

    def _source(self, name, kind, methodology):
        now = _now()
        self.conn.execute(
            "INSERT INTO sources (source,source_kind,methodology,first_seen,last_seen) "
            "VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET "
            "source_kind=excluded.source_kind, methodology=excluded.methodology, "
            "last_seen=excluded.last_seen",
            (name, kind, methodology, now, now),
        )

    def import_record_db(self, path):
        """Import official building facts from a `build_record.py` database."""
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = src.execute(
                "SELECT bbl, borough, address, zipcode, units_res, units_total, "
                "building_class, first_seen, last_seen FROM buildings"
            ).fetchall()
        finally:
            src.close()
        self._source("record_db", "public_record", "NYC public building facts imported from record.db")
        n = 0
        for bbl, borough, address, zipcode, units_res, units_total, building_class, first_seen, last_seen in rows:
            if not bbl:
                continue
            self.conn.execute(
                "INSERT INTO buildings (bbl,borough,primary_address,zipcode,units_res,units_total," 
                "building_class,source,first_seen,last_seen) VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(bbl) DO UPDATE SET borough=excluded.borough, "
                "primary_address=excluded.primary_address, zipcode=excluded.zipcode, "
                "units_res=excluded.units_res, units_total=excluded.units_total, "
                "building_class=excluded.building_class, last_seen=excluded.last_seen",
                (bbl, borough, address, zipcode, units_res, units_total, building_class, "record_db",
                 first_seen or _now(), last_seen or _now()),
            )
            normalized = normalize_address(address)
            if normalized:
                address_id = _id("addr", bbl, normalized)
                self.conn.execute(
                    "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET "
                    "address=excluded.address, zipcode=excluded.zipcode",
                    (address_id, bbl, address, normalized, zipcode, "record_db"),
                )
            n += 1
        self.conn.commit()
        return n

    def _bbl_candidates(self, address, zipcode):
        normalized = normalize_address(address)
        if not normalized:
            return [], "address could not be normalized"
        rows = self.conn.execute(
            "SELECT DISTINCT bbl FROM addresses WHERE normalized=? "
            "AND (? IS NULL OR zipcode=? OR zipcode IS NULL)",
            (normalized, zipcode, zipcode),
        ).fetchall()
        return [row[0] for row in rows], None

    def _resolve_bbl(self, address, zipcode):
        bbls, error = self._bbl_candidates(address, zipcode)
        if error:
            return None, "unresolved", 0.0, "normalized_address", error
        if len(bbls) == 1:
            return bbls[0], "resolved", 1.0, "exact_official_address", "exact normalized address matches one imported BBL"
        if not bbls:
            return None, "unresolved", 0.0, "exact_official_address", "no imported official address match"
        return None, "ambiguous", 0.0, "exact_official_address", "normalized address maps to multiple BBLs"

    def _record_bbl_candidates(self, observation_id, address, zipcode):
        bbls, error = self._bbl_candidates(address, zipcode)
        if len(bbls) < 2:
            return
        rationale = "exact normalized address maps to multiple official BBLs"
        self.conn.executemany(
            "INSERT OR IGNORE INTO entity_match_candidates "
            "(observation_id,entity_type,candidate_id,method,rationale) VALUES (?,?,?,?,?)",
            [(observation_id, "building", bbl, "exact_official_address", rationale) for bbl in bbls],
        )

    def _match(self, observation_id, entity_type, entity_id, status, confidence, method, rationale):
        self.conn.execute(
            "INSERT INTO entity_matches "
            "(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO UPDATE SET "
            "entity_id=excluded.entity_id,status=excluded.status,confidence=excluded.confidence,"
            "method=excluded.method,rationale=excluded.rationale,matched_at=excluded.matched_at",
            (observation_id, entity_type, entity_id, status, confidence, method, rationale, _now()),
        )

    def _ensure_building(self, bbl, source):
        """Ensure direct-BBL evidence has an entity to attach to without overwriting PLUTO."""
        now = _now()
        self.conn.execute(
            "INSERT OR IGNORE INTO buildings (bbl,source,first_seen,last_seen) VALUES (?,?,?,?)",
            (bbl, source, now, now),
        )

    def import_hpd_violations(self, limit=None, boro=None, offset=0):
        """Import HPD violations as official, unit-level evidence.

        HPD's raw dataset is used directly because `record.db` intentionally reduces
        violations to building events and therefore does not retain the apartment field
        or stable violation ID required for evidence-backed unit observations.
        """
        where = boro_clause(boro, "boroid", "code")
        rows = socrata(
            HPD_VIOLATIONS_DATASET, select=HPD_VIOLATIONS_SELECT, where=where,
            order="inspectiondate DESC", limit=limit, offset=offset,
        )
        source = "hpd_violations"
        self._source(source, "public_record", "NYC HPD Housing Maintenance Code Violations")
        retrieved_at = _now()
        observations = units = resolved = addressable_units = non_dwelling = unresolved = 0

        for row in rows:
            source_ref = str(row.get("violationid") or "")
            if not source_ref:
                # A source row without its immutable agency ID is retained nowhere:
                # it cannot be made idempotent or cited precisely enough for the catalog.
                continue
            bbl = make_bbl(row.get("boroid"), row.get("block"), row.get("lot"))
            observed_at = iso_date(row.get("novissueddate") or row.get("inspectiondate"))
            if not observed_at:
                observed_at = retrieved_at[:10]
            address = " ".join(
                str(value).strip() for value in (row.get("housenumber"), row.get("streetname")) if value
            ) or None
            raw_label = row.get("apartment")
            label_key = str(raw_label or "").strip().upper()
            normalized_label = normalize_unit(raw_label)
            document_id = _id("doc", source, source_ref, retrieved_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, retrieved_at,
                 json.dumps(row, default=str, sort_keys=True), "nyc_open_data_row"),
            )
            observation_id = _id("obs", source, source_ref, observed_at, "official_unit_mention")
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                "status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                "status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at, "official_unit_mention",
                 address, raw_label, row.get("violationstatus"), json.dumps(row, default=str, sort_keys=True),
                 "source_document"),
            )

            if not bbl:
                self._match(observation_id, "building", None, "unresolved", 0.0,
                            "official_bbl", "source row has no usable borough-block-lot identifier")
                self._match(observation_id, "unit", None, "unresolved", 0.0,
                            "official_bbl_and_unit_label", "source row has no usable BBL")
                unresolved += 1
            else:
                self._ensure_building(bbl, source)
                self._match(observation_id, "building", bbl, "resolved", 1.0,
                            "official_bbl", "BBL built directly from HPD borough, block, and lot")
                if address:
                    normalized_address = normalize_address(address)
                    if normalized_address:
                        self.conn.execute(
                            "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) "
                            "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET "
                            "address=excluded.address, zipcode=excluded.zipcode",
                            (_id("addr", bbl, normalized_address), bbl, address, normalized_address,
                             row.get("zip"), source),
                        )
                if label_key in NON_DWELLING_UNIT_LABELS:
                    self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                                "official_bbl_and_unit_label", "HPD apartment field names a common area")
                    non_dwelling += 1
                elif not normalized_label:
                    self._match(observation_id, "unit", None, "unresolved", 0.0,
                                "official_bbl_and_unit_label", "HPD record has no usable apartment label")
                    unresolved += 1
                else:
                    unit_id = _id("unit", bbl, normalized_label)
                    now = _now()
                    self.conn.execute(
                        "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                        "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                        (unit_id, bbl, raw_label, normalized_label, now, now),
                    )
                    self._match(observation_id, "unit", unit_id, "resolved", 1.0,
                                "official_bbl_and_unit_label",
                                "direct HPD BBL plus a non-common-area apartment label")
                    units += 1
                    resolved += 1
            observations += 1
        self.conn.commit()
        return {
            "hpd_offset": offset, "hpd_rows": len(rows), "hpd_observations": observations, "hpd_units": units,
            "hpd_resolved_unit_observations": resolved,
            "hpd_non_dwelling_observations": non_dwelling,
            "hpd_unresolved_unit_observations": unresolved,
        }

    def import_hpd_problems(self, limit=None, boro=None, offset=0,
                            before_date=None, before_problem_id=None):
        """Import HPD complaint problems with direct BBL and apartment labels."""
        where = boro_clause(boro, "borough", "name")
        if before_date:
            date = str(before_date).replace("'", "''")
            problem_id = str(before_problem_id or "").replace("'", "''")
            cursor_clause = "(received_date < '%s'" % date
            if problem_id:
                cursor_clause += " OR (received_date = '%s' AND problem_id < '%s')" % (date, problem_id)
            cursor_clause += ")"
            where = (where + " AND " if where else "") + cursor_clause
        rows = socrata(HPD_PROBLEMS_DATASET, select=HPD_PROBLEMS_SELECT, where=where,
                       order="received_date DESC, problem_id DESC", limit=limit, offset=offset)
        source = "hpd_problems"
        self._source(source, "public_record", "NYC HPD Housing Maintenance Code Complaints and Problems")
        retrieved_at = _now()
        observations = units = non_dwelling = unresolved = 0
        for row in rows:
            source_ref = str(row.get("problem_id") or "")
            observed_at = iso_date(row.get("received_date"))
            bbl = _normalize_bbl(row.get("bbl")) or make_bbl(row.get("borough"), row.get("block"), row.get("lot"))
            if not source_ref or not observed_at or not bbl:
                continue
            address = " ".join(str(v).strip() for v in (row.get("house_number"), row.get("street_name")) if v) or None
            raw_label = row.get("apartment")
            normalized_label = normalize_unit(raw_label)
            label_key = str(raw_label or "").strip().upper()
            payload = json.dumps(row, default=str, sort_keys=True)
            document_id = _id("doc", source, source_ref, retrieved_at)
            observation_id = _id("obs", source, source_ref, observed_at, "official_unit_mention")
            self.conn.execute("INSERT OR IGNORE INTO source_documents (document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                              (document_id, source, source_ref, retrieved_at, payload, "nyc_open_data_row"))
            self.conn.execute("INSERT INTO observations (observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                              (observation_id, document_id, source, source_ref, observed_at, "official_unit_mention", address, raw_label, row.get("problem_status") or row.get("complaint_status"), payload, "source_document"))
            self._ensure_building(bbl, source)
            self._match(observation_id, "building", bbl, "resolved", 1.0, "official_bbl", "BBL supplied by HPD problem source")
            if label_key in NON_DWELLING_UNIT_LABELS:
                self._match(observation_id, "unit", None, "not_a_dwelling", 0.0, "official_bbl_and_unit_label", "HPD problem names a common area or building-wide location")
                non_dwelling += 1
            elif not normalized_label:
                self._match(observation_id, "unit", None, "unresolved", 0.0, "official_bbl_and_unit_label", "HPD problem has no usable apartment label")
                unresolved += 1
            else:
                unit_id = _id("unit", bbl, normalized_label)
                now = _now()
                self.conn.execute("INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET unit_label=excluded.unit_label,last_seen=excluded.last_seen", (unit_id, bbl, raw_label, normalized_label, now, now))
                self._match(observation_id, "unit", unit_id, "resolved", 1.0, "official_bbl_and_unit_label", "direct HPD problem BBL plus apartment label")
                units += 1
            observations += 1
        self.conn.commit()
        tail = rows[-1] if rows else {}
        return {"hpd_problem_offset": offset, "hpd_problem_rows": len(rows), "hpd_problem_observations": observations,
                "hpd_problem_units": units, "hpd_problem_non_dwelling": non_dwelling,
                "hpd_problem_unresolved": unresolved,
                "hpd_problem_next_date": tail.get("received_date"),
                "hpd_problem_next_id": tail.get("problem_id")}

    def import_nycha_hmc_violations(self, limit=None, boro=None):
        """Import direct inspected-unit evidence from HPD's NYCHA violation dataset."""
        clauses = ["issued_in_err='N'"]
        if boro:
            clauses.append("boro='%s'" % boro)
        rows = socrata(NYCHA_HMC_VIOLATIONS_DATASET, select=NYCHA_HMC_VIOLATIONS_SELECT,
                       where=" AND ".join(clauses), order="viol_seq_no", limit=limit)
        source = "nycha_hmc_violations"
        self._source(source, "public_record", "NYC HPD Housing Maintenance Code Violations, NYCHA properties")
        retrieved_at = _now()
        observations = units = non_dwelling = unresolved = 0
        for row in rows:
            source_ref = str(row.get("viol_seq_no") or "")
            observed_at = iso_date(row.get("insp_dt") or row.get("viol_appr_dt"))
            bbl = _normalize_bbl(row.get("bbl")) or make_bbl(row.get("boro"), row.get("blk"), row.get("lot"))
            if not source_ref or not observed_at or not bbl:
                continue
            address = " ".join(str(v).strip() for v in (row.get("phn"), row.get("str_nm")) if v) or None
            raw_label = row.get("actl_unit_insp")
            label_key = str(raw_label or "").strip().upper()
            normalized_label = normalize_unit(raw_label)
            payload = json.dumps(row, default=str, sort_keys=True)
            document_id = _id("doc", source, source_ref, retrieved_at)
            observation_id = _id("obs", source, source_ref, observed_at, "official_nycha_hmc_violation")
            self.conn.execute("INSERT OR IGNORE INTO source_documents (document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)", (document_id, source, source_ref, retrieved_at, payload, "nyc_open_data_row"))
            self.conn.execute("INSERT INTO observations (observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade", (observation_id, document_id, source, source_ref, observed_at, "official_nycha_hmc_violation", address, raw_label, row.get("hzrd_clas"), payload, "source_document"))
            self._ensure_building(bbl, source)
            self._match(observation_id, "building", bbl, "resolved", 1.0, "official_bbl", "BBL supplied by NYCHA HMC violation source")
            if label_key in NON_DWELLING_UNIT_LABELS:
                self._match(observation_id, "unit", None, "not_a_dwelling", 0.0, "official_bbl_and_unit_label", "NYCHA inspection location is not a dwelling unit label")
                non_dwelling += 1
            elif not normalized_label:
                self._match(observation_id, "unit", None, "unresolved", 0.0, "official_bbl_and_unit_label", "NYCHA violation has no usable inspected unit label")
                unresolved += 1
            else:
                unit_id = _id("unit", bbl, normalized_label)
                now = _now()
                self.conn.execute("INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET unit_label=excluded.unit_label,last_seen=excluded.last_seen", (unit_id, bbl, raw_label, normalized_label, now, now))
                self._match(observation_id, "unit", unit_id, "resolved", 1.0, "official_bbl_and_unit_label", "direct NYCHA BBL plus inspected unit label")
                units += 1
            observations += 1
        self.conn.commit()
        return {"nycha_hmc_rows": len(rows), "nycha_hmc_observations": observations,
                "nycha_hmc_units": units, "nycha_hmc_non_dwelling": non_dwelling,
                "nycha_hmc_unresolved": unresolved}

    def import_ose_str_snapshot(self, path, snapshot_date):
        """Import an OSE published STR-registration XLSX snapshot.

        The release does not supply BBL, so a row becomes a canonical unit only when
        its published address resolves uniquely through previously imported official
        address evidence. The snapshot date is supplied explicitly from its filename.
        """
        source = "nyc_ose_str_registration_snapshot"
        self._source(source, "public_record", "NYC Office of Special Enforcement STR registration and listing snapshot")
        path = Path(path)
        file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        retrieved_at = _now()
        observations = units = unresolved = 0
        for ordinal, row in enumerate(read_xlsx_rows(path), start=2):
            def field(*names):
                return next((str(row.get(name) or "").strip() for name in names if str(row.get(name) or "").strip()), "")
            registration = field("Registration Number", "Registration #", "Registration_Number")
            listing = field("Listing ID", "Listing Id", "Listing_ID")
            address = field("Building Address", "Address", "Property Address")
            raw_label = field("Apartment/Unit", "Apartment / Unit", "Apartment", "Unit")
            zipcode = field("Zip Code", "ZIP", "Zip", "ZIP Code")
            source_ref = listing or registration or f"row-{ordinal}"
            payload = json.dumps({"snapshot_sha256": file_sha256, "snapshot_date": snapshot_date,
                                  "row_number": ordinal, "row": row}, sort_keys=True)
            document_id = _id("doc", source, source_ref, file_sha256)
            observation_id = _id("obs", source, source_ref, snapshot_date, "str_registration_listing")
            self.conn.execute("INSERT OR IGNORE INTO source_documents (document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                              (document_id, source, source_ref, retrieved_at, payload, "published_xlsx_row"))
            self.conn.execute("INSERT INTO observations (observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                              (observation_id, document_id, source, source_ref, snapshot_date, "str_registration_listing", address or None, raw_label or None, field("Registration Status", "Status") or None, payload, "source_document"))
            bbl, match_status, confidence, method, rationale = self._resolve_bbl(address, zipcode)
            self._match(observation_id, "building", bbl, match_status, confidence, method, rationale)
            normalized_label = normalize_unit(raw_label)
            if bbl and normalized_label:
                self._ensure_building(bbl, source)
                unit_id = _id("unit", bbl, normalized_label)
                now = _now()
                self.conn.execute("INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET unit_label=excluded.unit_label,last_seen=excluded.last_seen", (unit_id, bbl, raw_label, normalized_label, now, now))
                self._match(observation_id, "unit", unit_id, "resolved", 1.0, "unique_official_address_and_unit_label", "published STR snapshot address resolves to one official BBL")
                units += 1
            else:
                self._match(observation_id, "unit", None, "unresolved", 0.0, "unique_official_address_and_unit_label", "STR snapshot lacks a uniquely resolved BBL or usable unit label")
                unresolved += 1
            observations += 1
        self.conn.commit()
        return {"ose_str_snapshot_rows": observations, "ose_str_snapshot_units": units,
                "ose_str_snapshot_unresolved": unresolved, "ose_str_snapshot_sha256": file_sha256}

    def import_condo_units(self, limit=None, boro=None, offset=0):
        """Import DOF condominium unit tax lots without claiming they are apartments.

        `CONDO_BASE_BBL` is preserved exactly as the source's condo base/FKA lot. It
        is not relabeled as a billing or parent building BBL because the public schema
        does not make that equivalence.
        """
        rows = socrata(CONDO_UNITS_DATASET, select=CONDO_UNITS_SELECT,
                       order="unit_bbl", limit=limit, offset=offset)
        source = "nyc_dof_condo_units"
        self._source(source, "public_record", "NYC DOF Digital Tax Map: Condominium Units")
        retrieved_at = _now()
        imported = invalid = 0
        for row in rows:
            unit_lot_bbl = _normalize_bbl(row.get("unit_bbl"))
            if not unit_lot_bbl:
                invalid += 1
                continue
            base_bbl = _normalize_bbl(row.get("condo_base_bbl"))
            document_id = _id("doc", source, unit_lot_bbl, retrieved_at)
            payload = json.dumps(row, default=str, sort_keys=True)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, unit_lot_bbl, retrieved_at, payload, "nyc_open_data_row"),
            )
            observation_id = _id("obs", source, unit_lot_bbl, retrieved_at[:10], "official_condo_unit_lot")
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,"
                "status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,status=excluded.status,raw_fields=excluded.raw_fields,"
                "evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, unit_lot_bbl, retrieved_at[:10],
                 "official_condo_unit_lot", "reported", payload, "source_document"),
            )
            now = _now()
            self.conn.execute(
                "INSERT INTO official_unit_lots "
                "(unit_lot_bbl,condo_base_bbl,condo_number,condo_key,condo_base_bbl_key,unit_designation,"
                "floor_text,model,geometry_type,effective_tax_year,source,source_ref,document_id,"
                "record_status,first_seen,last_seen,raw_fields) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(unit_lot_bbl) DO UPDATE SET condo_base_bbl=excluded.condo_base_bbl,"
                "condo_number=excluded.condo_number,condo_key=excluded.condo_key,"
                "condo_base_bbl_key=excluded.condo_base_bbl_key,unit_designation=excluded.unit_designation,"
                "floor_text=excluded.floor_text,model=excluded.model,geometry_type=excluded.geometry_type,"
                "effective_tax_year=excluded.effective_tax_year,document_id=excluded.document_id,"
                "record_status=excluded.record_status,last_seen=excluded.last_seen,raw_fields=excluded.raw_fields",
                (unit_lot_bbl, base_bbl, row.get("condo_number"), row.get("condo_key"),
                 row.get("condo_base_bbl_key"), row.get("unit_designation"), row.get("floor_text"),
                 row.get("model"), row.get("geometry_type"), row.get("effective_tax_year"), source,
                 unit_lot_bbl, document_id, "reported", now, now, payload),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO official_unit_lot_links "
                "(unit_lot_bbl,unit_id,status,confidence,method,rationale,linked_at) VALUES (?,?,?,?,?,?,?)",
                (unit_lot_bbl, None, "unresolved", 0.0, "no_physical_unit_link",
                 "official condo tax lot has no verified resident-facing unit link", now),
            )
            if base_bbl:
                self._match(observation_id, "condo_base_lot", base_bbl, "resolved", 1.0,
                            "official_condo_base_bbl", "DOF condo base/FKA lot supplied by source")
            else:
                self._match(observation_id, "condo_base_lot", None, "unresolved", 0.0,
                            "official_condo_base_bbl", "source row has no usable condo base BBL")
            imported += 1
        self.conn.commit()
        return {"condo_offset": offset, "condo_rows": len(rows), "official_condo_unit_lots": imported,
                "invalid_condo_rows": invalid}

    def import_hpd_omo_work_orders(self, limit=None, boro=None, offset=0):
        """Import HPD Open Market Order charges as direct unit-level evidence.

        These are agency work orders issued under HPD enforcement programs. The
        source provides both a stable OMO ID and BBL/apartment fields, making it a
        stronger unit observation than a text-derived complaint. It remains an
        observation: it does not assert that every unit in the building is known.
        """
        where = boro_clause(boro, "boro_id", "code")
        rows = socrata(
            HPD_OMO_WORK_ORDERS_DATASET, select=HPD_OMO_WORK_ORDERS_SELECT,
            where=where, order="omocreatedate DESC", limit=limit, offset=offset,
        )
        source = "hpd_omo_work_orders"
        self._source(source, "public_record", "NYC HPD Open Market Order Charges")
        retrieved_at = _now()
        observations = units = resolved = addressable_units = non_dwelling = unresolved = 0
        for row in rows:
            source_ref = str(row.get("omoid") or "")
            if not source_ref:
                continue
            bbl = _normalize_bbl(row.get("bbl")) or make_bbl(
                row.get("boro_id"), row.get("block"), row.get("lot")
            )
            observed_at = iso_date(row.get("omocreatedate") or row.get("omoawarddate"))
            if not observed_at:
                observed_at = retrieved_at[:10]
            address = " ".join(
                str(value).strip() for value in (row.get("housenumber"), row.get("streetname")) if value
            ) or None
            raw_label = row.get("apartment")
            label_key = str(raw_label or "").strip().upper()
            normalized_label = normalize_unit(raw_label)
            document_id = _id("doc", source, source_ref, retrieved_at)
            payload = json.dumps(row, default=str, sort_keys=True)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, retrieved_at, payload, "nyc_open_data_row"),
            )
            observation_id = _id("obs", source, source_ref, observed_at, "official_unit_mention")
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                "status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                "status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at, "official_unit_mention",
                 address, raw_label, row.get("omostatusreason") or row.get("lifecycle"), payload,
                 "source_document"),
            )
            if not bbl:
                self._match(observation_id, "building", None, "unresolved", 0.0,
                            "official_bbl", "source row has no usable BBL")
                self._match(observation_id, "unit", None, "unresolved", 0.0,
                            "official_bbl_and_unit_label", "source row has no usable BBL")
                unresolved += 1
            else:
                self._ensure_building(bbl, source)
                self._match(observation_id, "building", bbl, "resolved", 1.0,
                            "official_bbl", "BBL supplied by HPD work-order source")
                if address and normalize_address(address):
                    normalized_address = normalize_address(address)
                    self.conn.execute(
                        "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET "
                        "address=excluded.address, zipcode=excluded.zipcode",
                        (_id("addr", bbl, normalized_address), bbl, address, normalized_address,
                         row.get("zip"), source),
                    )
                if label_key in NON_DWELLING_UNIT_LABELS:
                    self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                                "official_bbl_and_unit_label", "HPD work-order apartment field names a common area")
                    non_dwelling += 1
                elif not normalized_label:
                    self._match(observation_id, "unit", None, "unresolved", 0.0,
                                "official_bbl_and_unit_label", "HPD work-order row has no usable apartment label")
                    unresolved += 1
                else:
                    unit_id = _id("unit", bbl, normalized_label)
                    now = _now()
                    self.conn.execute(
                        "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                        "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                        (unit_id, bbl, raw_label, normalized_label, now, now),
                    )
                    self._match(observation_id, "unit", unit_id, "resolved", 1.0,
                                "official_bbl_and_unit_label",
                                "direct HPD work-order BBL plus a non-common-area apartment label")
                    units += 1
                    resolved += 1
            observations += 1
        self.conn.commit()
        return {
            "hpd_omo_offset": offset, "hpd_omo_rows": len(rows), "hpd_omo_observations": observations, "hpd_omo_units": units,
            "hpd_omo_resolved_unit_observations": resolved,
            "hpd_omo_non_dwelling_observations": non_dwelling,
            "hpd_omo_unresolved_unit_observations": unresolved,
        }

    def import_acris_property_legals(self, limit=None, boro=None, offset=0, unit_only=False,
                                     before_document_id=None):
        """Import ACRIS legal-property rows as official historic unit observations.

        The Legals table associates an ACRIS document and BBL with a street address
        and, when present, a unit label. `good_through_date` is the source snapshot
        date, not the document recording date, so the observation says only what this
        public legal index reported at that time.
        """
        where = boro_clause(boro, "borough", "code")
        if unit_only:
            unit_clause = "unit IS NOT NULL AND unit <> ''"
            where = f"({where}) AND {unit_clause}" if where else unit_clause
        if before_document_id is not None:
            cursor = str(before_document_id).replace("'", "''")
            clause = f"document_id <= '{cursor}'"
            where = f"({where}) AND {clause}" if where else clause
        rows = socrata(
            ACRIS_PROPERTY_LEGALS_DATASET, select=ACRIS_PROPERTY_LEGALS_SELECT,
            where=where, order="document_id DESC", limit=limit, offset=offset,
        )
        stats = self._ingest_acris_legal_rows(rows)
        stats.update({
            "acris_legal_offset": offset,
            "acris_legal_rows": len(rows),
            "acris_legal_next_document_id": min(
                (str(row.get("document_id")) for row in rows if row.get("document_id")), default=None
            ),
        })
        return stats

    def _ingest_acris_legal_rows(self, rows):
        """Resolve already-acquired ACRIS rows while retaining each raw source row."""
        source = "acris_property_legals"
        self._source(source, "public_record", "NYC ACRIS Real Property Legals")
        retrieved_at = _now()
        observations = units = resolved = addressable_units = non_dwelling = unresolved = 0
        for row in rows:
            document_number = str(row.get("document_id") or "")
            bbl = make_bbl(row.get("borough"), row.get("block"), row.get("lot"))
            if not document_number or not bbl:
                continue
            payload = json.dumps(row, default=str, sort_keys=True)
            # One legal document can cover several lots and several apartments on
            # one lot. Retain the full source-row identity so a later unit label
            # cannot overwrite a sibling label from the same document and BBL.
            source_ref = f"{document_number}:{bbl}:{_id('row', payload).split('_', 1)[1]}"
            observed_at = iso_date(row.get("good_through_date")) or retrieved_at[:10]
            address = " ".join(
                str(value).strip() for value in (row.get("street_number"), row.get("street_name")) if value
            ) or None
            raw_label = row.get("unit")
            label_key = str(raw_label or "").strip().upper()
            normalized_label = normalize_unit(raw_label)
            document_id = _id("doc", source, source_ref, retrieved_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, retrieved_at, payload, "nyc_open_data_row"),
            )
            observation_id = _id("obs", source, source_ref, observed_at, "official_unit_mention")
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                "status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                "status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at, "official_unit_mention",
                 address, raw_label, row.get("property_type"), payload, "source_document"),
            )
            self._ensure_building(bbl, source)
            self._match(observation_id, "building", bbl, "resolved", 1.0,
                        "official_bbl", "BBL built directly from ACRIS borough, block, and lot")
            if address and normalize_address(address):
                normalized_address = normalize_address(address)
                self.conn.execute(
                    "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET address=excluded.address",
                    (_id("addr", bbl, normalized_address), bbl, address, normalized_address, None, source),
                )
            if label_key in NON_DWELLING_UNIT_LABELS:
                self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                            "official_bbl_and_unit_label", "ACRIS unit field names a non-dwelling space")
                non_dwelling += 1
            elif not normalized_label:
                self._match(observation_id, "unit", None, "unresolved", 0.0,
                            "official_bbl_and_unit_label", "ACRIS legal row has no usable unit label")
                unresolved += 1
            else:
                unit_id = _id("unit", bbl, normalized_label)
                now = _now()
                self.conn.execute(
                    "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                    "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                    (unit_id, bbl, raw_label, normalized_label, now, now),
                )
                self._match(observation_id, "unit", unit_id, "resolved", 1.0,
                            "official_bbl_and_unit_label", "direct ACRIS BBL plus legal unit label")
                if address:
                    normalized_address = normalize_address(address)
                    official = self.conn.execute(
                        "SELECT address,zipcode FROM addresses WHERE bbl=? AND normalized=? AND source='nyc_pad'",
                        (bbl, normalized_address),
                    ).fetchone()
                    if official:
                        premise_id = _id("premise", bbl, normalized_address)
                        self.conn.execute(
                            "INSERT INTO premises (premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                            (premise_id, bbl, official[0], normalized_address, official[1], "nyc_pad", now, now),
                        )
                        addressable_unit_id = _id("addressable_unit", premise_id, normalized_label)
                        self.conn.execute(
                            "INSERT INTO addressable_units "
                            "(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
                            "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET "
                            "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                            (addressable_unit_id, premise_id, raw_label, normalized_label, now, now),
                        )
                        self._match(observation_id, "addressable_unit", addressable_unit_id, "resolved", 1.0,
                                    "official_bbl_exact_pad_address_and_unit_label",
                                    "direct ACRIS BBL plus an ACRIS address that exactly matches PAD and a unit label")
                        addressable_units += 1
                units += 1
                resolved += 1
            observations += 1
        self.conn.commit()
        return {
            "acris_legal_observations": observations,
            "acris_legal_units": units, "acris_legal_resolved_unit_observations": resolved,
            "acris_legal_addressable_units": addressable_units,
            "acris_legal_non_dwelling_observations": non_dwelling,
            "acris_legal_unresolved_unit_observations": unresolved,
        }

    def import_acris_unit_legals(self, limit=None, boro=None, offset=0, before_document_id=None):
        """Acquire only ACRIS legal rows that can carry an apartment label.

        This is intentionally a distinct acquisition lane from the historical
        unfiltered scan: its offsets are against a different, identity-bearing
        source universe and must never share a resume checkpoint.
        """
        return self.import_acris_property_legals(
            limit=limit, boro=boro, offset=offset, unit_only=True,
            before_document_id=before_document_id,
        )

    def import_staged_acris_unit_legals(self, stage_path, limit=1000):
        """Resolve a bounded batch from the immutable ACRIS raw-source stage.

        The stage is marked resolved only after catalog commits. A crash between the
        two is safe: reprocessing rows is idempotent through source-row identities.
        """
        if limit <= 0:
            raise ValueError("stage limit must be positive")
        stage = sqlite3.connect(f"file:{Path(stage_path).resolve()}?mode=rw", uri=True, timeout=30)
        try:
            records = stage.execute(
                "SELECT row_id,raw_payload FROM staged_acris_unit_legals WHERE resolved_at IS NULL "
                "ORDER BY document_id DESC, row_id LIMIT ?", (limit,)
            ).fetchall()
            rows = [json.loads(record[1]) for record in records]
            stats = self._ingest_acris_legal_rows(rows)
            if records:
                stage.executemany(
                    "UPDATE staged_acris_unit_legals SET resolved_at=? WHERE row_id=?",
                    [(_now(), record[0]) for record in records],
                )
                stage.commit()
            stats.update({
                "acris_stage_rows": len(records),
                "acris_stage_rows_remaining": stage.execute(
                    "SELECT COUNT(*) FROM staged_acris_unit_legals WHERE resolved_at IS NULL"
                ).fetchone()[0],
            })
            return stats
        finally:
            stage.close()

    def import_vayo_all_nyc_units(self, path, limit=10000, after_unit_id=None):
        """Import a bounded page of Vayo's archived all-NYC-unit evidence.

        This archive is a secondary aggregation, not an official unit roster. Its
        direct BBL and retained source-system fields support a BBL/unit identity,
        while its address is retained only as an observation for later exact-PAD
        premise resolution. Placeholder rows and known scraper artifacts never
        create units or capacity claims.
        """
        if limit <= 0:
            raise ValueError("limit must be positive")
        archive_path = Path(path).resolve()
        if not archive_path.exists():
            raise FileNotFoundError(archive_path)
        snapshot_at = datetime.fromtimestamp(archive_path.stat().st_mtime, timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        source = "vayo_all_nyc_units_archive"
        if after_unit_id is None:
            state = self.conn.execute(
                "SELECT cursor_ref FROM archive_import_progress WHERE source=?", (source,)
            ).fetchone()
            after_unit_id = state[0] if state and state[0] else None
        src = sqlite3.connect(f"file:{archive_path}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        try:
            rows = src.execute(
                "SELECT unit_id,bbl,borough,address,zipcode,unit_number,is_placeholder,"
                "source_systems,confidence_score,ownership_type,bldgclass,yearbuilt,numfloors "
                "FROM all_nyc_units WHERE is_placeholder=0 AND unit_number IS NOT NULL "
                "AND unit_id>? ORDER BY unit_id LIMIT ?",
                (after_unit_id or "", limit),
            ).fetchall()
        finally:
            src.close()

        self._source(
            source, "archived_secondary_source",
            "Vayo all_nyc_units archival export; retained source_systems and raw rows, never used as capacity",
        )
        observations = units = addressable_units = text_mined = non_dwelling = invalid_bbl = 0
        for row in rows:
            raw = dict(row)
            bbl = _normalize_bbl(raw["bbl"])
            raw_label = raw["unit_number"]
            label_key = str(raw_label or "").strip().upper()
            normalized_label = normalize_unit(raw_label)
            if not bbl:
                invalid_bbl += 1
                continue
            if (not normalized_label or label_key in NON_DWELLING_UNIT_LABELS or
                    label_key in VAYO_NON_UNIT_LABELS):
                non_dwelling += 1
                continue
            source_ref = str(raw["unit_id"])
            payload = json.dumps(raw, default=str, sort_keys=True)
            document_id = _id("doc", source, source_ref, snapshot_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, snapshot_at, payload, "archived_vayo_unit_row"),
            )
            observed_at = raw.get("discovered_at") or snapshot_at[:10]
            observation_id = _id("obs", source, source_ref, observed_at, "archived_unit_mention")
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                "status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                "status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at, "archived_unit_mention",
                 raw["address"], raw_label, raw["source_systems"], payload, "archived_secondary_source"),
            )
            self._ensure_building(bbl, source)
            self._match(observation_id, "building", bbl, "resolved", 0.9,
                        "archived_direct_bbl", "Vayo archival row retains a direct BBL")
            source_systems = str(raw.get("source_systems") or "")
            if "TEXT_MINED" in source_systems.upper():
                self._match(observation_id, "unit", None, "unresolved", 0.0,
                            "archived_text_mined_unit_label",
                            "Vayo identifies this label as text-mined; retain it as a lead pending a primary source")
                observations += 1
                text_mined += 1
                continue
            unit_id = _id("unit", bbl, normalized_label)
            now = _now()
            self.conn.execute(
                "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                (unit_id, bbl, raw_label, normalized_label, now, now),
            )
            self._match(observation_id, "unit", unit_id, "resolved", 0.8,
                        "archived_bbl_and_unit_label",
                        "Vayo archival row retains a direct BBL, unit label, and source-system metadata")
            normalized_address = normalize_address(raw["address"])
            if normalized_address:
                official = self.conn.execute(
                    "SELECT address,zipcode FROM addresses WHERE bbl=? AND normalized=? AND source='nyc_pad'",
                    (bbl, normalized_address),
                ).fetchone()
                if official:
                    premise_id = _id("premise", bbl, normalized_address)
                    self.conn.execute(
                        "INSERT INTO premises (premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                        (premise_id, bbl, official[0], normalized_address, official[1], "nyc_pad", now, now),
                    )
                    addressable_unit_id = _id("addressable_unit", premise_id, normalized_label)
                    self.conn.execute(
                        "INSERT INTO addressable_units "
                        "(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET "
                        "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                        (addressable_unit_id, premise_id, raw_label, normalized_label, now, now),
                    )
                    self._match(observation_id, "addressable_unit", addressable_unit_id, "resolved", 0.8,
                                "exact_pad_address_and_archived_unit_label",
                                "Vayo archival address exactly matches PAD on its retained direct BBL")
                    addressable_units += 1
            observations += 1
            units += 1
        if rows:
            self.conn.execute(
                "INSERT INTO archive_import_progress (source,cursor_ref,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(source) DO UPDATE SET cursor_ref=excluded.cursor_ref,updated_at=excluded.updated_at",
                (source, rows[-1]["unit_id"], _now()),
            )
        self.conn.commit()
        return {
            "vayo_archive_rows": len(rows),
            "vayo_archive_observations": observations,
            "vayo_archive_units": units,
            "vayo_archive_addressable_units": addressable_units,
            "vayo_archive_text_mined_rows": text_mined,
            "vayo_archive_non_dwelling_rows": non_dwelling,
            "vayo_archive_invalid_bbl_rows": invalid_bbl,
            "vayo_archive_next_unit_id": rows[-1]["unit_id"] if rows else after_unit_id,
        }

    def demote_vayo_text_mined_units(self):
        """Remove canonical claims made solely from Vayo's explicitly text-mined rows.

        The observations and raw archive documents remain. A unit survives when a
        different resolved observation supports it; otherwise it returns to the
        unresolved evidence pool until a direct source is acquired.
        """
        self.conn.executescript(
            "DROP TABLE IF EXISTS temp.vayo_text_mined_observations;"
            "DROP TABLE IF EXISTS temp.vayo_text_mined_unit_ids;"
            "DROP TABLE IF EXISTS temp.vayo_text_mined_addressable_ids;"
            "DROP TABLE IF EXISTS temp.vayo_supported_unit_ids;"
            "DROP TABLE IF EXISTS temp.vayo_supported_addressable_ids;"
            "CREATE TEMP TABLE vayo_text_mined_observations AS "
            "SELECT observation_id FROM observations WHERE source='vayo_all_nyc_units_archive' "
            "AND raw_fields LIKE '%TEXT_MINED%';"
            "CREATE TEMP TABLE vayo_text_mined_unit_ids AS "
            "SELECT entity_id FROM entity_matches WHERE entity_type='unit' AND status='resolved' "
            "AND observation_id IN (SELECT observation_id FROM vayo_text_mined_observations);"
            "CREATE TEMP TABLE vayo_text_mined_addressable_ids AS "
            "SELECT entity_id FROM entity_matches WHERE entity_type='addressable_unit' AND status='resolved' "
            "AND observation_id IN (SELECT observation_id FROM vayo_text_mined_observations);"
        )
        unit_claims = self.conn.execute("SELECT COUNT(*) FROM vayo_text_mined_unit_ids").fetchone()[0]
        addressable_claims = self.conn.execute(
            "SELECT COUNT(*) FROM vayo_text_mined_addressable_ids"
        ).fetchone()[0]
        now = _now()
        rationale = "Vayo identifies this label as text-mined; retain it as a lead pending a primary source"
        self.conn.execute(
            "UPDATE entity_matches SET entity_id=NULL,status='unresolved',confidence=0.0,"
            "method='archived_text_mined_unit_label',rationale=?,matched_at=? WHERE entity_type='unit' "
            "AND observation_id IN (SELECT observation_id FROM vayo_text_mined_observations)",
            (rationale, now),
        )
        self.conn.execute(
            "UPDATE entity_matches SET entity_id=NULL,status='unresolved',confidence=0.0,"
            "method='archived_text_mined_unit_label',rationale=?,matched_at=? WHERE entity_type='addressable_unit' "
            "AND observation_id IN (SELECT observation_id FROM vayo_text_mined_observations)",
            (rationale, now),
        )
        self.conn.executescript(
            "CREATE TEMP TABLE vayo_supported_unit_ids AS SELECT DISTINCT entity_id FROM entity_matches "
            "WHERE entity_type='unit' AND status='resolved' AND entity_id IN "
            "(SELECT entity_id FROM vayo_text_mined_unit_ids);"
            "CREATE TEMP TABLE vayo_supported_addressable_ids AS SELECT DISTINCT entity_id FROM entity_matches "
            "WHERE entity_type='addressable_unit' AND status='resolved' AND entity_id IN "
            "(SELECT entity_id FROM vayo_text_mined_addressable_ids);"
        )
        self.conn.execute(
            "DELETE FROM addressable_units WHERE addressable_unit_id IN "
            "(SELECT entity_id FROM vayo_text_mined_addressable_ids) AND addressable_unit_id NOT IN "
            "(SELECT entity_id FROM vayo_supported_addressable_ids)"
        )
        self.conn.execute(
            "DELETE FROM units WHERE unit_id IN (SELECT entity_id FROM vayo_text_mined_unit_ids) "
            "AND unit_id NOT IN (SELECT entity_id FROM vayo_supported_unit_ids)"
        )
        self.conn.commit()
        return {
            "vayo_text_mined_unit_claims_demoted": unit_claims,
            "vayo_text_mined_addressable_claims_demoted": addressable_claims,
            "canonical_units_remaining": self.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0],
            "addressable_units_remaining": self.conn.execute("SELECT COUNT(*) FROM addressable_units").fetchone()[0],
        }

    def import_vayo_streeteasy_unit_summary(self, path, limit=10000, after_id=None):
        """Import archived StreetEasy unit-history rows from Vayo's source store.

        The archive retains the public building URL and event fields, but no BBL.
        A row becomes a unit only after its building address maps exactly to PAD;
        otherwise it remains an attributable historical observation with candidates.
        """
        if limit <= 0:
            raise ValueError("limit must be positive")
        archive_path = Path(path).resolve()
        if not archive_path.exists():
            raise FileNotFoundError(archive_path)
        source = "vayo_streeteasy_unit_summary_archive"
        if after_id is None:
            state = self.conn.execute(
                "SELECT cursor_ref FROM archive_import_progress WHERE source=?", (source,)
            ).fetchone()
            after_id = state[0] if state and state[0] else "0"
        try:
            after_id = int(after_id)
        except (TypeError, ValueError):
            raise ValueError("StreetEasy archive cursor must be an integer row id")
        snapshot_at = datetime.fromtimestamp(archive_path.stat().st_mtime, timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        src = sqlite3.connect(f"file:{archive_path}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        try:
            rows = src.execute(
                "SELECT us.id,us.building_slug,us.unit,us.listing_type,us.date,us.price,us.price_numeric,"
                "us.status,us.beds,us.baths,us.sqft,us.sqft_numeric,us.asking_price,us.discount_pct,"
                "us.scraped_at,us.availability,b.address,b.url AS building_url,b.status AS building_status "
                "FROM unit_summary us JOIN buildings b ON b.slug=us.building_slug "
                "WHERE us.id>? AND us.unit IS NOT NULL AND trim(us.unit)<>'' ORDER BY us.id LIMIT ?",
                (after_id, limit),
            ).fetchall()
        finally:
            src.close()
        self._source(
            source, "archived_secondary_source",
            "Vayo archival StreetEasy unit-summary rows with public building URLs; resolved only through PAD",
        )
        observations = units = addressable_units = unresolved = non_dwelling = 0
        for row in rows:
            raw = dict(row)
            raw_label = raw["unit"]
            label_key = str(raw_label).strip().upper()
            normalized_label = normalize_unit(raw_label)
            source_ref = str(raw["id"])
            payload = json.dumps(raw, default=str, sort_keys=True)
            document_id = _id("doc", source, source_ref, snapshot_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, snapshot_at, payload, "archived_streeteasy_unit_summary"),
            )
            observed_at = iso_date(raw["date"]) or iso_date(raw["scraped_at"]) or snapshot_at[:10]
            observation_id = _id("obs", source, source_ref, observed_at, "archived_listing_history")
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                "bedrooms,bathrooms,price,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                "bedrooms=excluded.bedrooms,bathrooms=excluded.bathrooms,price=excluded.price,status=excluded.status,"
                "raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at, "archived_listing_history",
                 raw["address"], raw_label, raw["beds"], raw["baths"], raw["price_numeric"], raw["status"],
                 payload, "archived_secondary_source"),
            )
            bbl, match_status, confidence, method, rationale = self._resolve_bbl(raw["address"], None)
            self._match(observation_id, "building", bbl, match_status, confidence, method, rationale)
            self._record_bbl_candidates(observation_id, raw["address"], None)
            if label_key in NON_DWELLING_UNIT_LABELS or not normalized_label:
                self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                            "archived_exact_address_and_unit_label",
                            "StreetEasy archive label is blank or names a non-dwelling space")
                non_dwelling += 1
            elif not bbl:
                self._match(observation_id, "unit", None, match_status, 0.0,
                            "archived_exact_address_and_unit_label", rationale)
                unresolved += 1
            else:
                unit_id = _id("unit", bbl, normalized_label)
                now = _now()
                self.conn.execute(
                    "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                    "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                    (unit_id, bbl, raw_label, normalized_label, now, now),
                )
                self._match(observation_id, "unit", unit_id, "resolved", 0.8,
                            "archived_exact_address_and_unit_label",
                            "StreetEasy archive address maps exactly to PAD plus a usable unit label")
                official = self.conn.execute(
                    "SELECT address,zipcode FROM addresses WHERE bbl=? AND normalized=? AND source='nyc_pad'",
                    (bbl, normalize_address(raw["address"])),
                ).fetchone()
                if official:
                    premise_id = _id("premise", bbl, normalize_address(raw["address"]))
                    self.conn.execute(
                        "INSERT INTO premises (premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                        (premise_id, bbl, official[0], normalize_address(raw["address"]), official[1], "nyc_pad", now, now),
                    )
                    addressable_unit_id = _id("addressable_unit", premise_id, normalized_label)
                    self.conn.execute(
                        "INSERT INTO addressable_units "
                        "(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET "
                        "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                        (addressable_unit_id, premise_id, raw_label, normalized_label, now, now),
                    )
                    self._match(observation_id, "addressable_unit", addressable_unit_id, "resolved", 0.8,
                                "archived_exact_pad_address_and_unit_label",
                                "StreetEasy archive address exactly matches PAD plus a usable unit label")
                    addressable_units += 1
                units += 1
            observations += 1
        if rows:
            self.conn.execute(
                "INSERT INTO archive_import_progress (source,cursor_ref,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(source) DO UPDATE SET cursor_ref=excluded.cursor_ref,updated_at=excluded.updated_at",
                (source, str(rows[-1]["id"]), _now()),
            )
        self.conn.commit()
        return {
            "vayo_streeteasy_rows": len(rows),
            "vayo_streeteasy_observations": observations,
            "vayo_streeteasy_units": units,
            "vayo_streeteasy_addressable_units": addressable_units,
            "vayo_streeteasy_unresolved": unresolved,
            "vayo_streeteasy_non_dwelling": non_dwelling,
            "vayo_streeteasy_next_id": rows[-1]["id"] if rows else after_id,
        }

    def import_vayo_elliman_mls_archive(self, path, limit=10000, after_listing_id=None):
        """Import Vayo's archived Elliman MLS history with PAD-only resolution.

        The archival database contains broker contact fields, which are deliberately
        excluded from the retained payload. The catalog stores the listing's stable
        ID, address/unit, dates, price/status, and MLS provenance only.
        """
        if limit <= 0:
            raise ValueError("limit must be positive")
        archive_path = Path(path).resolve()
        if not archive_path.exists():
            raise FileNotFoundError(archive_path)
        source = "vayo_elliman_mls_archive"
        if after_listing_id is None:
            state = self.conn.execute(
                "SELECT cursor_ref FROM archive_import_progress WHERE source=?", (source,)
            ).fetchone()
            after_listing_id = state[0] if state and state[0] else ""
        snapshot_at = datetime.fromtimestamp(archive_path.stat().st_mtime, timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        src = sqlite3.connect(f"file:{archive_path}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        try:
            rows = src.execute(
                "SELECT core_listing_id,address,unit,zip,listing_status,listing_type,home_type,ownership_type,"
                "list_price,close_price,list_date,close_date,update_date,bedrooms,bathrooms_total,living_area_sqft,"
                "year_built,building_name,source_mls,fetched_at FROM listings "
                "WHERE core_listing_id>? ORDER BY core_listing_id LIMIT ?",
                (after_listing_id, limit),
            ).fetchall()
        finally:
            src.close()
        from ..adapters.elliman import _address_and_unit

        self._source(
            source, "archived_secondary_source",
            "Vayo archival Elliman MLS rows; source payload excludes archived broker contact fields and resolves only through PAD",
        )
        observations = units = addressable_units = unresolved = non_dwelling = 0
        address_resolution_cache = {}
        for row in rows:
            raw = dict(row)
            source_ref = str(raw["core_listing_id"])
            address, raw_label = _address_and_unit({
                "samlsFullAddress": raw["address"], "unitNumber": raw["unit"],
            })
            label_key = str(raw_label or "").strip().upper()
            normalized_label = normalize_unit(raw_label)
            payload = json.dumps(raw, default=str, sort_keys=True)
            document_id = _id("doc", source, source_ref, snapshot_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, snapshot_at, payload, "archived_elliman_mls_listing"),
            )
            observed_at = (iso_date(raw["close_date"]) or iso_date(raw["list_date"]) or
                           iso_date(raw["update_date"]) or iso_date(raw["fetched_at"]) or snapshot_at[:10])
            observation_id = _id("obs", source, source_ref, observed_at, "archived_listing_history")
            price = raw["close_price"] if raw["close_price"] is not None else raw["list_price"]
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                "bedrooms,bathrooms,price,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                "bedrooms=excluded.bedrooms,bathrooms=excluded.bathrooms,price=excluded.price,status=excluded.status,"
                "raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at, "archived_listing_history",
                 address, raw_label, raw["bedrooms"], raw["bathrooms_total"], price, raw["listing_status"],
                 payload, "archived_secondary_source"),
            )
            resolution_key = (normalize_address(address), raw["zip"])
            resolution = address_resolution_cache.get(resolution_key)
            if resolution is None:
                bbl, match_status, confidence, method, rationale = self._resolve_bbl(address, raw["zip"])
                candidates, _ = self._bbl_candidates(address, raw["zip"])
                resolution = (bbl, match_status, confidence, method, rationale, candidates)
                address_resolution_cache[resolution_key] = resolution
            bbl, match_status, confidence, method, rationale, candidates = resolution
            self._match(observation_id, "building", bbl, match_status, confidence, method, rationale)
            if len(candidates) >= 2:
                candidate_rationale = "exact normalized address maps to multiple official BBLs"
                self.conn.executemany(
                    "INSERT OR IGNORE INTO entity_match_candidates "
                    "(observation_id,entity_type,candidate_id,method,rationale) VALUES (?,?,?,?,?)",
                    [(observation_id, "building", candidate, "exact_official_address", candidate_rationale)
                     for candidate in candidates],
                )
            if label_key in NON_DWELLING_UNIT_LABELS or not normalized_label:
                self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                            "archived_exact_address_and_unit_label",
                            "Elliman archive label is blank or names a non-dwelling space")
                non_dwelling += 1
            elif not bbl:
                self._match(observation_id, "unit", None, match_status, 0.0,
                            "archived_exact_address_and_unit_label", rationale)
                unresolved += 1
            else:
                unit_id = _id("unit", bbl, normalized_label)
                now = _now()
                self.conn.execute(
                    "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                    "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                    (unit_id, bbl, raw_label, normalized_label, now, now),
                )
                self._match(observation_id, "unit", unit_id, "resolved", 0.8,
                            "archived_exact_address_and_unit_label",
                            "Elliman archive address maps exactly to PAD plus a usable unit label")
                normalized_address = normalize_address(address)
                official = self.conn.execute(
                    "SELECT address,zipcode FROM addresses WHERE bbl=? AND normalized=? AND source='nyc_pad'",
                    (bbl, normalized_address),
                ).fetchone()
                if official:
                    premise_id = _id("premise", bbl, normalized_address)
                    self.conn.execute(
                        "INSERT INTO premises (premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                        (premise_id, bbl, official[0], normalized_address, official[1], "nyc_pad", now, now),
                    )
                    addressable_unit_id = _id("addressable_unit", premise_id, normalized_label)
                    self.conn.execute(
                        "INSERT INTO addressable_units "
                        "(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET "
                        "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                        (addressable_unit_id, premise_id, raw_label, normalized_label, now, now),
                    )
                    self._match(observation_id, "addressable_unit", addressable_unit_id, "resolved", 0.8,
                                "archived_exact_pad_address_and_unit_label",
                                "Elliman archive address exactly matches PAD plus a usable unit label")
                    addressable_units += 1
                units += 1
            observations += 1
        if rows:
            self.conn.execute(
                "INSERT INTO archive_import_progress (source,cursor_ref,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(source) DO UPDATE SET cursor_ref=excluded.cursor_ref,updated_at=excluded.updated_at",
                (source, rows[-1]["core_listing_id"], _now()),
            )
        self.conn.commit()
        return {
            "vayo_elliman_rows": len(rows),
            "vayo_elliman_observations": observations,
            "vayo_elliman_units": units,
            "vayo_elliman_addressable_units": addressable_units,
            "vayo_elliman_unresolved": unresolved,
            "vayo_elliman_non_dwelling": non_dwelling,
            "vayo_elliman_next_id": rows[-1]["core_listing_id"] if rows else after_listing_id,
        }

    def import_vayo_corcoran_archive(self, path, limit=10000, after_listing_id=None):
        """Import Vayo's archived Corcoran listing history with exact-PAD resolution.

        The archive is public-listing history but contains agent and detail fields.
        Only listing-level identifiers, location, unit, date, price, and status are
        retained in the catalog's provenance payload.
        """
        if limit <= 0:
            raise ValueError("limit must be positive")
        archive_path = Path(path).resolve()
        if not archive_path.exists():
            raise FileNotFoundError(archive_path)
        source = "vayo_corcoran_archive"
        if after_listing_id is None:
            state = self.conn.execute(
                "SELECT cursor_ref FROM archive_import_progress WHERE source=?", (source,)
            ).fetchone()
            after_listing_id = state[0] if state and state[0] else ""
        snapshot_at = datetime.fromtimestamp(archive_path.stat().st_mtime, timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        src = sqlite3.connect(f"file:{archive_path}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        try:
            rows = src.execute(
                "SELECT listing_id,property_id,source_id,listing_status,transaction_type,listing_type,"
                "building_type,property_type,ownership,unit_type,address1,address2,zip_code,borough,neighborhood,"
                "price,bedrooms,bathrooms,total_bathrooms,square_footage,closed_rented_date,detail_fetched,fetched_at "
                "FROM listings WHERE listing_id>? ORDER BY listing_id LIMIT ?",
                (after_listing_id, limit),
            ).fetchall()
        finally:
            src.close()
        from ..adapters.elliman import _address_and_unit

        self._source(
            source, "archived_secondary_source",
            "Vayo archival Corcoran listing rows; source payload excludes archived broker contacts and detail JSON, resolved only through PAD",
        )
        observations = units = addressable_units = unresolved = non_dwelling = 0
        address_resolution_cache = {}
        for row in rows:
            raw = dict(row)
            source_ref = str(raw["listing_id"])
            address, raw_label = _address_and_unit({
                "samlsFullAddress": raw["address1"], "unitNumber": raw["address2"] or raw["unit_type"],
            })
            label_key = str(raw_label or "").strip().upper()
            normalized_label = normalize_unit(raw_label)
            payload = json.dumps(raw, default=str, sort_keys=True)
            document_id = _id("doc", source, source_ref, snapshot_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, snapshot_at, payload, "archived_corcoran_listing"),
            )
            observed_at = (iso_date(raw["closed_rented_date"]) or iso_date(raw["fetched_at"]) or snapshot_at[:10])
            observation_id = _id("obs", source, source_ref, observed_at, "archived_listing_history")
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                "bedrooms,bathrooms,price,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                "bedrooms=excluded.bedrooms,bathrooms=excluded.bathrooms,price=excluded.price,status=excluded.status,"
                "raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at, "archived_listing_history",
                 address, raw_label, raw["bedrooms"], raw["total_bathrooms"] or raw["bathrooms"], raw["price"],
                 raw["listing_status"], payload, "archived_secondary_source"),
            )
            resolution_key = (normalize_address(address), raw["zip_code"])
            resolution = address_resolution_cache.get(resolution_key)
            if resolution is None:
                bbl, match_status, confidence, method, rationale = self._resolve_bbl(address, raw["zip_code"])
                candidates, _ = self._bbl_candidates(address, raw["zip_code"])
                resolution = (bbl, match_status, confidence, method, rationale, candidates)
                address_resolution_cache[resolution_key] = resolution
            bbl, match_status, confidence, method, rationale, candidates = resolution
            self._match(observation_id, "building", bbl, match_status, confidence, method, rationale)
            if len(candidates) >= 2:
                candidate_rationale = "exact normalized address maps to multiple official BBLs"
                self.conn.executemany(
                    "INSERT OR IGNORE INTO entity_match_candidates "
                    "(observation_id,entity_type,candidate_id,method,rationale) VALUES (?,?,?,?,?)",
                    [(observation_id, "building", candidate, "exact_official_address", candidate_rationale)
                     for candidate in candidates],
                )
            if label_key in NON_DWELLING_UNIT_LABELS or not normalized_label:
                self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                            "archived_exact_address_and_unit_label",
                            "Corcoran archive label is blank or names a non-dwelling space")
                non_dwelling += 1
            elif not bbl:
                self._match(observation_id, "unit", None, match_status, 0.0,
                            "archived_exact_address_and_unit_label", rationale)
                unresolved += 1
            else:
                unit_id = _id("unit", bbl, normalized_label)
                now = _now()
                self.conn.execute(
                    "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                    "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                    (unit_id, bbl, raw_label, normalized_label, now, now),
                )
                self._match(observation_id, "unit", unit_id, "resolved", 0.8,
                            "archived_exact_address_and_unit_label",
                            "Corcoran archive address maps exactly to PAD plus a usable unit label")
                normalized_address = normalize_address(address)
                official = self.conn.execute(
                    "SELECT address,zipcode FROM addresses WHERE bbl=? AND normalized=? AND source='nyc_pad'",
                    (bbl, normalized_address),
                ).fetchone()
                if official:
                    premise_id = _id("premise", bbl, normalized_address)
                    self.conn.execute(
                        "INSERT INTO premises (premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                        (premise_id, bbl, official[0], normalized_address, official[1], "nyc_pad", now, now),
                    )
                    addressable_unit_id = _id("addressable_unit", premise_id, normalized_label)
                    self.conn.execute(
                        "INSERT INTO addressable_units "
                        "(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET "
                        "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                        (addressable_unit_id, premise_id, raw_label, normalized_label, now, now),
                    )
                    self._match(observation_id, "addressable_unit", addressable_unit_id, "resolved", 0.8,
                                "archived_exact_pad_address_and_unit_label",
                                "Corcoran archive address exactly matches PAD plus a usable unit label")
                    addressable_units += 1
                units += 1
            observations += 1
        if rows:
            self.conn.execute(
                "INSERT INTO archive_import_progress (source,cursor_ref,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(source) DO UPDATE SET cursor_ref=excluded.cursor_ref,updated_at=excluded.updated_at",
                (source, rows[-1]["listing_id"], _now()),
            )
        self.conn.commit()
        return {
            "vayo_corcoran_rows": len(rows),
            "vayo_corcoran_observations": observations,
            "vayo_corcoran_units": units,
            "vayo_corcoran_addressable_units": addressable_units,
            "vayo_corcoran_unresolved": unresolved,
            "vayo_corcoran_non_dwelling": non_dwelling,
            "vayo_corcoran_next_id": rows[-1]["listing_id"] if rows else after_listing_id,
        }

    def _import_dof_sales(self, dataset, select, source, methodology, metric_prefix,
                          limit=None, boro=None, offset=0):
        """Import a DOF sale feed as dated, official unit observations when labeled.

        The annualized sales table has no immutable row ID. Its source reference is a
        deterministic hash of the public fields that distinguish one reported sale;
        source payload remains available to audit that identity choice.
        """
        where = boro_clause(boro, "borough", "code")
        rows = socrata(dataset, select=select,
                       where=where, order="sale_date DESC", limit=limit, offset=offset)
        self._source(source, "public_record", methodology)
        retrieved_at = _now()
        observations = units = resolved = non_dwelling = unresolved = 0
        for row in rows:
            bbl = _normalize_bbl(row.get("bbl")) or make_bbl(
                row.get("borough"), row.get("block"), row.get("lot")
            )
            observed_at = iso_date(row.get("sale_date"))
            if not bbl or not observed_at:
                continue
            raw_address = str(row.get("address") or "").strip()
            address = raw_address
            raw_label = row.get("apartment_number")
            source_label = raw_label
            label_source = "apartment_number"
            normalized_label = normalize_unit(raw_label)
            # Co-op sale addresses often repeat the apartment after a final comma.
            # The field is official evidence, but the parser is intentionally narrow.
            if normalized_label and "," in raw_address:
                head, tail = raw_address.rsplit(",", 1)
                if normalize_unit(tail) == normalized_label:
                    address = head.strip()
            elif not normalized_label and "," in raw_address:
                head, tail = raw_address.rsplit(",", 1)
                candidate = normalize_unit(tail)
                if head.strip() and _DOF_ADDRESS_UNIT.fullmatch(candidate):
                    address = head.strip()
                    raw_label = tail.strip()
                    normalized_label = candidate
                    label_source = "address_suffix"
            label_key = str(raw_label or "").strip().upper()
            # Keep the source identity tied to the published columns so a rerun
            # upgrades an existing unresolved row instead of duplicating it.
            source_ref = _id("sale", bbl, observed_at, raw_address, source_label, row.get("sale_price"))
            document_id = _id("doc", source, source_ref, retrieved_at)
            payload = json.dumps(row, default=str, sort_keys=True)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, retrieved_at, payload, "nyc_open_data_row"),
            )
            observation_id = _id("obs", source, source_ref, observed_at, "official_sale")
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                "price,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                "price=excluded.price,status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at, "official_sale", address or None,
                 raw_label, row.get("sale_price"), row.get("building_class_category"), payload, "source_document"),
            )
            self._ensure_building(bbl, source)
            self._match(observation_id, "building", bbl, "resolved", 1.0,
                        "official_bbl", "BBL supplied by DOF annualized sales source")
            if address and normalize_address(address):
                normalized_address = normalize_address(address)
                self.conn.execute(
                    "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET "
                    "address=excluded.address, zipcode=excluded.zipcode",
                    (_id("addr", bbl, normalized_address), bbl, address, normalized_address,
                     row.get("zip_code"), source),
                )
            if label_key in NON_DWELLING_UNIT_LABELS:
                self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                            "official_bbl_and_unit_label", "DOF sale apartment field names a non-dwelling space")
                non_dwelling += 1
            elif not normalized_label:
                self._match(observation_id, "unit", None, "unresolved", 0.0,
                            "official_bbl_and_unit_label", "DOF sale row has no usable apartment label")
                unresolved += 1
            else:
                unit_id = _id("unit", bbl, normalized_label)
                now = _now()
                self.conn.execute(
                    "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                    "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                    (unit_id, bbl, raw_label, normalized_label, now, now),
                )
                rationale = "direct DOF sale BBL plus apartment number"
                method = "official_bbl_and_unit_label"
                if label_source == "address_suffix":
                    rationale = "DOF sale address explicitly includes a comma-delimited apartment label"
                    method = "official_bbl_and_address_unit_label"
                self._match(observation_id, "unit", unit_id, "resolved", 1.0,
                            method, rationale)
                units += 1
                resolved += 1
            observations += 1
        self.conn.commit()
        return {
            f"{metric_prefix}_offset": offset, f"{metric_prefix}_rows": len(rows),
            f"{metric_prefix}_observations": observations,
            f"{metric_prefix}_units": units,
            f"{metric_prefix}_resolved_unit_observations": resolved,
            f"{metric_prefix}_non_dwelling_observations": non_dwelling,
            f"{metric_prefix}_unresolved_unit_observations": unresolved,
        }

    def import_annualized_sales(self, limit=None, boro=None, offset=0):
        """Import DOF's historical annualized calendar-sales table."""
        return self._import_dof_sales(
            ANNUALIZED_SALES_DATASET, ANNUALIZED_SALES_SELECT, "dof_annualized_sales",
            "NYC DOF Annualized Calendar Sales", "annualized_sale", limit, boro, offset,
        )

    def import_rolling_sales(self, limit=None, boro=None, offset=0):
        """Import DOF's current rolling calendar-sales table."""
        return self._import_dof_sales(
            ROLLING_SALES_DATASET, ROLLING_SALES_SELECT, "dof_rolling_sales",
            "NYC DOF Rolling Sales Update", "rolling_sale", limit, boro, offset,
        )

    def import_evictions(self, limit=None, boro=None, offset=0):
        """Import residential executed-possession records without personal names.

        NYC DOI's dataset is an incomplete record of marshal-reported executed events,
        not a tenant history or a finding about either party. The stored payload is an
        allowlist that deliberately omits marshal names.
        """
        where = "residential_commercial_ind='Residential'"
        if boro:
            where += " AND " + boro_clause(boro, "borough", "name")
        rows = socrata(EVICTIONS_DATASET, select=EVICTIONS_SELECT, where=where,
                       order="executed_date DESC", limit=limit, offset=offset)
        source = "nyc_evictions"
        self._source(source, "public_record", "NYC DOI Marshal Evictions, residential rows only")
        retrieved_at = _now()
        observations = units = resolved = non_dwelling = unresolved = 0
        for row in rows:
            observed_at = iso_date(row.get("executed_date"))
            if not observed_at:
                continue
            # These exact selected fields are the privacy-minimized source payload.
            payload = json.dumps(row, default=str, sort_keys=True)
            source_ref = _id("eviction", payload)
            bbl = _normalize_bbl(row.get("bbl"))
            address = row.get("eviction_address")
            raw_label = row.get("eviction_apt_num")
            label_key = str(raw_label or "").strip().upper()
            normalized_label = normalize_unit(raw_label)
            document_id = _id("doc", source, source_ref, retrieved_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, retrieved_at, payload, "nyc_open_data_row_redacted"),
            )
            observation_id = _id("obs", source, source_ref, observed_at, "official_eviction_event")
            status = " / ".join(
                str(value) for value in (row.get("eviction_possession"), row.get("ejectment")) if value
            ) or None
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                "status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                "status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at, "official_eviction_event",
                 address, raw_label, status, payload, "source_document"),
            )
            if not bbl:
                matched_bbl, match_status, confidence, method, rationale = self._resolve_bbl(
                    address, row.get("eviction_zip")
                )
                self._match(observation_id, "building", matched_bbl, match_status, confidence, method, rationale)
                if match_status == "ambiguous":
                    self._record_bbl_candidates(observation_id, address, row.get("eviction_zip"))
                unresolved += 1
                self._match(observation_id, "unit", None, "unresolved", 0.0,
                            "official_bbl_and_unit_label", "eviction row has no usable BBL")
            else:
                self._ensure_building(bbl, source)
                self._match(observation_id, "building", bbl, "resolved", 1.0,
                            "official_bbl", "BBL supplied by NYC DOI eviction source")
                if address and normalize_address(address):
                    normalized_address = normalize_address(address)
                    self.conn.execute(
                        "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET "
                        "address=excluded.address, zipcode=excluded.zipcode",
                        (_id("addr", bbl, normalized_address), bbl, address, normalized_address,
                         row.get("eviction_zip"), source),
                    )
                if label_key in NON_DWELLING_UNIT_LABELS or label_key.endswith(" FLOOR"):
                    self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                                "official_bbl_and_unit_label", "eviction apartment field is a common-area or floor label")
                    non_dwelling += 1
                elif not normalized_label:
                    self._match(observation_id, "unit", None, "unresolved", 0.0,
                                "official_bbl_and_unit_label", "eviction row has no usable apartment label")
                    unresolved += 1
                else:
                    unit_id = _id("unit", bbl, normalized_label)
                    now = _now()
                    self.conn.execute(
                        "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                        "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                        (unit_id, bbl, raw_label, normalized_label, now, now),
                    )
                    self._match(observation_id, "unit", unit_id, "resolved", 1.0,
                                "official_bbl_and_unit_label", "direct DOI BBL plus apartment label")
                    units += 1
                    resolved += 1
            observations += 1
        self.conn.commit()
        return {
            "eviction_offset": offset, "eviction_rows": len(rows), "eviction_observations": observations,
            "eviction_units": units, "eviction_resolved_unit_observations": resolved,
            "eviction_non_dwelling_observations": non_dwelling,
            "eviction_unresolved_unit_observations": unresolved,
        }

    def _import_dob_now_unit_events(self, dataset, select, source, methodology,
                                    observation_kind, metric_prefix, date_fields,
                                    status_field, source_ref_fields, limit=None,
                                    boro=None, offset=0):
        """Import DOB NOW apartment mentions from one dated public event feed.

        A job location can name several apartments. Each label becomes a separately
        auditable observation tied to the same raw filing payload; no filing implies
        that all other units in the building are known.
        """
        where = "borough='%s'" % BOROUGHS[boro][1].title() if boro else None
        rows = socrata(dataset, select=select, where=where,
                       order=f"{date_fields[0]} DESC", limit=limit, offset=offset)
        self._source(source, "public_record", methodology)
        retrieved_at = _now()
        observations = units = resolved = non_dwelling = unresolved = 0
        for row in rows:
            primary_ref = str(row.get("job_filing_number") or "")
            bbl = _normalize_bbl(row.get("bbl")) or make_bbl(
                row.get("borough"), row.get("block"), row.get("lot")
            )
            if not primary_ref:
                continue
            observed_at = next((iso_date(row.get(field)) for field in date_fields if iso_date(row.get(field))), None)
            observed_at = observed_at or retrieved_at[:10]
            address = " ".join(
                str(value).strip() for value in (row.get("house_no"), row.get("street_name")) if value
            ) or None
            raw_labels = str(row.get("apt_condo_no_s") or "").strip()
            labels = [part.strip() for part in re.split(r"[,;/]", raw_labels) if part.strip()]
            if not labels:
                labels = [None]
            payload = json.dumps(row, default=str, sort_keys=True)
            document_ref = _id("dob_event", *(row.get(field) for field in source_ref_fields))
            document_id = _id("doc", source, document_ref, retrieved_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, document_ref, retrieved_at, payload, "nyc_open_data_row"),
            )
            for raw_label in labels:
                normalized_label = normalize_unit(raw_label)
                label_key = str(raw_label or "").strip().upper()
                source_ref = _id("dob_unit_event", document_ref, normalized_label or "no_unit")
                observation_id = _id("obs", source, source_ref, observed_at, observation_kind)
                self.conn.execute(
                    "INSERT INTO observations "
                    "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                    "status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                    "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                    "status=excluded.status,raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                    (observation_id, document_id, source, source_ref, observed_at, observation_kind,
                     address, raw_label, row.get(status_field), payload, "source_document"),
                )
                if not bbl:
                    self._match(observation_id, "building", None, "unresolved", 0.0,
                                "official_bbl", "DOB job row has no usable BBL")
                    self._match(observation_id, "unit", None, "unresolved", 0.0,
                                "official_bbl_and_unit_label", "DOB job row has no usable BBL")
                    unresolved += 1
                else:
                    self._ensure_building(bbl, source)
                    self._match(observation_id, "building", bbl, "resolved", 1.0,
                                "official_bbl", "BBL supplied by DOB NOW job filing")
                    if address and normalize_address(address):
                        normalized_address = normalize_address(address)
                        self.conn.execute(
                            "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) "
                            "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET "
                            "address=excluded.address, zipcode=excluded.zipcode",
                            (_id("addr", bbl, normalized_address), bbl, address, normalized_address,
                             row.get("postcode") or row.get("zip_code"), source),
                        )
                    if label_key in NON_DWELLING_UNIT_LABELS or label_key in {"ALL", "N/A", "NA"}:
                        self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                                    "official_bbl_and_unit_label", "DOB job location is not a dwelling unit label")
                        non_dwelling += 1
                    elif not normalized_label:
                        self._match(observation_id, "unit", None, "unresolved", 0.0,
                                    "official_bbl_and_unit_label", "DOB event has no usable apartment label")
                        unresolved += 1
                    else:
                        unit_id = _id("unit", bbl, normalized_label)
                        now = _now()
                        self.conn.execute(
                            "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                            "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                            "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                            (unit_id, bbl, raw_label, normalized_label, now, now),
                        )
                        self._match(observation_id, "unit", unit_id, "resolved", 1.0,
                                    "official_bbl_and_unit_label", "direct DOB event BBL plus apartment label")
                        units += 1
                        resolved += 1
                observations += 1
        self.conn.commit()
        return {
            f"{metric_prefix}_offset": offset, f"{metric_prefix}_rows": len(rows),
            f"{metric_prefix}_observations": observations, f"{metric_prefix}_units": units,
            f"{metric_prefix}_resolved_unit_observations": resolved,
            f"{metric_prefix}_non_dwelling_observations": non_dwelling,
            f"{metric_prefix}_unresolved_unit_observations": unresolved,
        }

    def import_dob_now_jobs(self, limit=None, boro=None, offset=0):
        """Import DOB NOW job-level apartment mentions as official observations."""
        return self._import_dob_now_unit_events(
            DOB_NOW_JOBS_DATASET, DOB_NOW_JOBS_SELECT, "dob_now_job_filings",
            "NYC DOB NOW Build Job Application Filings", "official_job_filing", "dob_job",
            ("filing_date", "current_status_date"), "filing_status", ("job_filing_number",),
            limit, boro, offset,
        )

    def import_dob_now_permits(self, limit=None, boro=None, offset=0):
        """Import DOB NOW approved-permit apartment mentions as official observations."""
        return self._import_dob_now_unit_events(
            DOB_NOW_PERMITS_DATASET, DOB_NOW_PERMITS_SELECT, "dob_now_approved_permits",
            "NYC DOB NOW Build Approved Permits", "official_approved_permit", "dob_permit",
            ("issued_date", "approved_date"), "permit_status",
            ("job_filing_number", "work_permit", "issued_date", "apt_condo_no_s"),
            limit, boro, offset,
        )

    def import_dob_now_certificates(self, limit=None, boro=None, offset=0):
        """Import DOB NOW certificates as building-level capacity evidence.

        Certificates report a dwelling-unit count but do not provide apartment
        labels. They therefore enrich building evidence only and never create
        canonical unit rows.
        """
        where = "borough='%s'" % BOROUGHS[boro][1].title() if boro else None
        rows = socrata(DOB_NOW_CERTIFICATES_DATASET, select=DOB_NOW_CERTIFICATES_SELECT,
                       where=where, order="c_of_o_issuance_date DESC", limit=limit, offset=offset)
        source = "dob_now_certificates"
        self._source(source, "public_record", "NYC DOB NOW Certificates of Occupancy")
        retrieved_at = _now()
        observations = resolved = unresolved = 0
        for row in rows:
            source_ref = str(row.get("c_of_o_number") or row.get("application_number") or row.get("job_filing_name") or "")
            if not source_ref:
                continue
            bbl = _normalize_bbl(row.get("bbl")) or make_bbl(row.get("borough"), row.get("block"), row.get("lot"))
            observed_at = iso_date(row.get("c_of_o_issuance_date")) or iso_date(row.get("submitted_date")) or retrieved_at[:10]
            address = " ".join(str(value).strip() for value in (row.get("house_no"), row.get("street_name")) if value) or None
            payload = json.dumps(row, default=str, sort_keys=True)
            document_id = _id("doc", source, source_ref, retrieved_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, retrieved_at, payload, "nyc_open_data_row"),
            )
            observation_id = _id("obs", source, source_ref, observed_at, "official_certificate_of_occupancy")
            self.conn.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,status,raw_fields,evidence_grade) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                "document_id=excluded.document_id,address=excluded.address,status=excluded.status,raw_fields=excluded.raw_fields,"
                "evidence_grade=excluded.evidence_grade",
                (observation_id, document_id, source, source_ref, observed_at,
                 "official_certificate_of_occupancy", address, row.get("c_of_o_status"), payload, "source_document"),
            )
            if bbl:
                self._ensure_building(bbl, source)
                self._match(observation_id, "building", bbl, "resolved", 1.0, "official_bbl",
                            "DOB NOW certificate supplies BBL or borough-block-lot")
                resolved += 1
            else:
                self._match(observation_id, "building", None, "unresolved", 0.0, "official_bbl",
                            "DOB NOW certificate has no usable BBL")
                unresolved += 1
            observations += 1
        self.conn.commit()
        return {"dob_certificate_offset": offset, "dob_certificate_rows": len(rows),
                "dob_certificate_observations": observations,
                "dob_certificate_resolved_buildings": resolved,
                "dob_certificate_unresolved_buildings": unresolved}

    def import_hpd_registration_coverage(self, limit=None, boro=None, offset=0):
        """Create an immutable registered-rental coverage snapshot.

        HPD registration membership and PLUTO `units_res` are coverage context only.
        A label-count delta is a diagnostic, never proof that a particular apartment
        exists or is absent.
        """
        where = boro_clause(boro, "boroid", "code")
        rows = socrata(HPD_REGISTRATIONS_DATASET, select=HPD_REGISTRATIONS_SELECT,
                       where=where, order="registrationid", limit=limit, offset=offset)
        source = "hpd_multiple_dwelling_registrations"
        self._source(source, "public_record", "NYC HPD Multiple Dwelling Registrations")
        now = _now()
        as_of_date = now[:10]
        scope = BOROUGHS[boro][0] if boro else "citywide"
        run_id = _id("coverage", source, scope, as_of_date, now)
        status = "partial" if limit is not None else "complete"
        self.conn.execute(
            "INSERT INTO coverage_runs (run_id,scope,as_of_date,status,hpd_rows,started_at) VALUES (?,?,?,?,?,?)",
            (run_id, scope, as_of_date, "running", len(rows), now),
        )
        for row in rows:
            registration_id = str(row.get("registrationid") or "")
            if not registration_id:
                continue
            bbl = make_bbl(row.get("boroid"), row.get("block"), row.get("lot"))
            end_date = iso_date(row.get("registrationenddate"))
            if not end_date:
                timing_status = "missing_expiration"
            elif end_date >= as_of_date:
                timing_status = "unexpired_at_run"
            else:
                timing_status = "expired_at_run"
            address = " ".join(
                str(value).strip() for value in (row.get("housenumber"), row.get("streetname")) if value
            ) or None
            payload = json.dumps(row, default=str, sort_keys=True)
            document_id = _id("doc", source, registration_id, now)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, registration_id, now, payload, "nyc_open_data_row"),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO coverage_hpd_registrations "
                "(run_id,registration_id,bbl,hpd_building_id,address,zipcode,registration_end_date,timing_status,document_id,raw_fields) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run_id, registration_id, bbl, row.get("buildingid"), address, row.get("zip"), end_date,
                 timing_status, document_id, payload),
            )
        self.conn.execute(
            """
            INSERT INTO building_coverage
            (run_id,bbl,membership_status,pluto_units_res,canonical_unit_labels,official_unit_labels,listing_unit_labels)
            WITH hpd AS (
                SELECT bbl, MAX(timing_status='unexpired_at_run') AS unexpired
                FROM coverage_hpd_registrations WHERE run_id=? AND bbl IS NOT NULL GROUP BY bbl
            ), lots AS (
                SELECT bbl, units_res FROM buildings WHERE units_res IS NOT NULL AND units_res > 0
            ), unit_counts AS (
                SELECT u.bbl,
                    COUNT(*) AS canonical_units,
                    COUNT(DISTINCT CASE WHEN s.source_kind='public_record' THEN u.unit_id END) AS official_units,
                    COUNT(DISTINCT CASE WHEN s.source_kind='listing_feed' THEN u.unit_id END) AS listing_units
                FROM units u
                LEFT JOIN entity_matches m ON m.entity_type='unit' AND m.entity_id=u.unit_id AND m.status='resolved'
                LEFT JOIN observations o ON o.observation_id=m.observation_id
                LEFT JOIN sources s ON s.source=o.source
                GROUP BY u.bbl
            ), bbls AS (SELECT bbl FROM hpd UNION SELECT bbl FROM lots)
            SELECT ?, b.bbl,
                CASE
                    WHEN h.unexpired=1 AND l.units_res > 0 THEN 'hpd_unexpired_pluto_residential'
                    WHEN h.unexpired=1 THEN 'hpd_unexpired_no_positive_pluto_count'
                    WHEN h.bbl IS NOT NULL AND l.units_res > 0 THEN 'hpd_expired_pluto_residential'
                    WHEN l.units_res > 0 THEN 'pluto_residential_not_hpd_unexpired'
                    ELSE 'hpd_only_no_pluto_lot'
                END,
                l.units_res, COALESCE(u.canonical_units,0), COALESCE(u.official_units,0), COALESCE(u.listing_units,0)
            FROM bbls b LEFT JOIN hpd h ON h.bbl=b.bbl LEFT JOIN lots l ON l.bbl=b.bbl
            LEFT JOIN unit_counts u ON u.bbl=b.bbl
            """,
            (run_id, run_id),
        )
        self.conn.execute(
            "UPDATE coverage_runs SET status=?, completed_at=? WHERE run_id=?", (status, _now(), run_id)
        )
        self.conn.commit()
        return {"coverage_run_id": run_id, "coverage_scope": scope, "coverage_status": status,
                "hpd_registration_offset": offset, "hpd_registration_rows": len(rows), "covered_bbls": self.conn.execute(
                    "SELECT COUNT(*) FROM building_coverage WHERE run_id=?", (run_id,)).fetchone()[0]}

    def import_pad_addresses(self, zips=None, limit=None):
        """Import NYC PAD's official alternate addresses for a ZIP scope or citywide.

        PAD is the fuller address directory behind the crosswalk engine. It improves
        resolution of existing listing observations without asserting any new units.
        ZIP scope limits the large public archive to active geography; an explicit
        ``None`` scope builds the citywide address backbone.
        """
        zips = sorted({str(zipcode).strip() for zipcode in zips if str(zipcode).strip()}) if zips else None
        source = "nyc_pad"
        self._source(source, "public_record", "NYC Property Address Directory alternate addresses")
        retrieved_at = _now()
        document_id = _id("doc", source, "bc8t-ecyu", retrieved_at)
        self.conn.execute(
            "INSERT OR IGNORE INTO source_documents "
            "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
            (document_id, source, "bc8t-ecyu", retrieved_at,
             json.dumps({"dataset_id": "bc8t-ecyu", "zips": zips}, sort_keys=True),
             "nyc_open_data_archive"),
        )
        crosswalk_added = build_crosswalk_pad(self.conn, zips=zips, limit=limit)
        query = "SELECT DISTINCT norm_address, bbl, zipcode FROM crosswalk"
        params = ()
        if zips:
            query += " WHERE zipcode IN (%s)" % ",".join("?" for _ in zips)
            params = tuple(zips)
        rows = self.conn.execute(query, params).fetchall()
        addresses = 0
        for normalized, bbl, zipcode in rows:
            self._ensure_building(bbl, source)
            self.conn.execute(
                "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET "
                "address=excluded.address, zipcode=excluded.zipcode",
                (_id("addr", bbl, normalized), bbl, normalized, normalized, zipcode, source),
            )
            addresses += 1
        self.conn.commit()
        return {"pad_crosswalk_rows_added": crosswalk_added, "pad_addresses_in_scope": addresses,
                "pad_zipcodes": len(zips) if zips else "citywide"}

    def listing_zipcodes(self, listings_path):
        """Return ZIPs represented by active scraped listings, sorted for reproducibility."""
        src = sqlite3.connect(f"file:{listings_path}?mode=ro", uri=True)
        try:
            rows = src.execute(
                "SELECT DISTINCT zipcode FROM listings WHERE status='active' "
                "AND zipcode IS NOT NULL AND TRIM(zipcode) != '' ORDER BY zipcode"
            ).fetchall()
        finally:
            src.close()
        return [row[0] for row in rows]

    def listing_coverage(self, listings_path):
        """Current active listing resolution coverage, grouped by source and ZIP.

        This intentionally counts raw source listings, not catalog entities: it answers
        how much of the scraped inventory is currently grounded to a canonical unit.
        """
        self.conn.execute("ATTACH DATABASE ? AS listing_source", (str(listings_path),))
        try:
            rows = self.conn.execute(
                """
                WITH resolved AS (
                    SELECT DISTINCT o.source, o.source_ref
                    FROM observations o
                    JOIN entity_matches m ON m.observation_id=o.observation_id
                    WHERE o.observation_kind='listing' AND m.entity_type='unit'
                      AND m.status='resolved'
                )
                SELECT l.source, COALESCE(NULLIF(TRIM(l.zipcode), ''), 'unknown') AS zipcode,
                       COUNT(*) AS listings,
                       SUM(CASE WHEN r.source_ref IS NOT NULL THEN 1 ELSE 0 END) AS resolved
                FROM listing_source.listings l
                LEFT JOIN resolved r ON r.source=l.source AND r.source_ref=l.source_id
                WHERE l.status='active'
                GROUP BY l.source, COALESCE(NULLIF(TRIM(l.zipcode), ''), 'unknown')
                ORDER BY listings DESC, l.source, zipcode
                """
            ).fetchall()
        finally:
            self.conn.execute("DETACH DATABASE listing_source")
        return [
            {"source": source, "zipcode": zipcode, "listings": listings, "resolved": resolved,
             "unresolved": listings - resolved,
             "resolution_rate": (resolved / listings) if listings else 0.0}
            for source, zipcode, listings, resolved in rows
        ]

    def reconcile_unit_candidates(self):
        """Resolve ambiguous listings only with unique official unit corroboration.

        A listing's address may map to several BBLs. It becomes resolved only when a
        direct HPD violation observation has already resolved the same normalized
        unit label at the same normalized address on exactly one retained candidate
        BBL. Other listings, other public records, different entrances, and common
        areas are intentionally not corroboration here.
        """
        rows = self.conn.execute(
            """
            SELECT o.observation_id, o.address, o.unit_label
            FROM observations o
            JOIN entity_matches um ON um.observation_id=o.observation_id
            JOIN entity_matches bm ON bm.observation_id=o.observation_id
            WHERE o.observation_kind='listing' AND um.entity_type='unit'
              AND um.status='ambiguous' AND bm.entity_type='building'
              AND bm.status='ambiguous'
            """
        ).fetchall()
        scanned = resolved = no_unit = still_ambiguous = 0
        for observation_id, address, unit_label in rows:
            scanned += 1
            normalized_unit = normalize_unit(unit_label)
            normalized_address = normalize_address(address)
            if (not normalized_unit or not normalized_address or
                    str(unit_label or "").strip().upper() in NON_DWELLING_UNIT_LABELS):
                no_unit += 1
                continue
            evidence = self.conn.execute(
                """
                SELECT c.candidate_id, u.unit_id, eo.observation_id, eo.source_ref, eo.address
                FROM entity_match_candidates c
                JOIN units u ON u.bbl=c.candidate_id AND u.normalized_unit=?
                JOIN entity_matches em ON em.entity_type='unit' AND em.entity_id=u.unit_id
                                   AND em.status='resolved'
                                   AND em.method='official_bbl_and_unit_label'
                JOIN observations eo ON eo.observation_id=em.observation_id
                WHERE c.observation_id=? AND c.entity_type='building'
                  AND eo.source='hpd_violations'
                  AND eo.observation_kind='official_unit_mention'
                  AND eo.evidence_grade='source_document'
                  AND eo.address IS NOT NULL
                """,
                (normalized_unit, observation_id),
            ).fetchall()
            evidence = [row for row in evidence if normalize_address(row[4]) == normalized_address]
            if not evidence:
                still_ambiguous += 1
                continue
            candidates = {row[0] for row in evidence}
            if len(candidates) != 1:
                still_ambiguous += 1
                continue
            bbl = next(iter(candidates))
            unit_ids = {row[1] for row in evidence}
            if len(unit_ids) != 1:
                still_ambiguous += 1
                continue
            unit_id = next(iter(unit_ids))
            source_refs = ", ".join(sorted({str(row[3]) for row in evidence}))
            rationale = (
                "HPD violation(s) %s corroborate this unit at exactly one retained BBL candidate"
                % source_refs
            )
            self._match(observation_id, "building", bbl, "resolved", 0.98,
                        "unique_official_unit_corroboration", rationale)
            self._match(observation_id, "unit", unit_id, "resolved", 0.98,
                        "unique_official_unit_corroboration", rationale)
            self.conn.executemany(
                "INSERT OR IGNORE INTO entity_match_evidence "
                "(observation_id,entity_type,evidence_observation_id,role) VALUES (?,?,?,?)",
                [(observation_id, "building", row[2], "corroborates_candidate") for row in evidence] +
                [(observation_id, "unit", row[2], "corroborates_candidate") for row in evidence],
            )
            resolved += 1
        self.conn.commit()
        return {"ambiguous_listing_observations_scanned": scanned,
                "candidate_units_resolved": resolved,
                "candidate_units_without_usable_label": no_unit,
                "candidate_units_still_ambiguous": still_ambiguous}

    def import_listings_db(self, path):
        """Import listing snapshots without fabricating evidence for older pulls.

        The existing `price_history` table preserves prior price snapshots, but predates
        this catalog and does not contain a raw response per day. Those rows are marked
        `legacy_snapshot`; the current listing row becomes a source document carrying
        its unmodified `raw_json`.
        """
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        try:
            listings = src.execute("SELECT * FROM listings").fetchall()
            history = src.execute("SELECT * FROM price_history").fetchall()
        finally:
            src.close()
        history_by_ref = {}
        for row in history:
            history_by_ref.setdefault((row["source"], row["source_id"]), []).append(row)

        observations = units = resolved = unresolved = 0
        for listing in listings:
            source = listing["source"]
            source_ref = str(listing["source_id"])
            self._source(source, "listing_feed", "public landlord or brokerage availability feed")
            retrieved_at = listing["last_seen"] or _now()
            document_id = _id("doc", source, source_ref, retrieved_at)
            self.conn.execute(
                "INSERT OR IGNORE INTO source_documents "
                "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                (document_id, source, source_ref, retrieved_at, listing["raw_json"], "upstream_listing_json"),
            )
            bbl, match_status, confidence, method, rationale = self._resolve_bbl(
                listing["address"], listing["zipcode"]
            )
            normalized_unit = normalize_unit(listing["unit_number"])
            is_non_dwelling = str(listing["unit_number"] or "").strip().upper() in NON_DWELLING_UNIT_LABELS
            unit_id = None
            if bbl and normalized_unit and not is_non_dwelling:
                unit_id = _id("unit", bbl, normalized_unit)
                now = _now()
                self.conn.execute(
                    "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
                    "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                    (unit_id, bbl, listing["unit_number"], normalized_unit, now, now),
                )
                units += 1

            snapshots = history_by_ref.get((source, source_ref)) or [listing]
            for snapshot in snapshots:
                observed_at = snapshot["snapshot_date"] if "snapshot_date" in snapshot.keys() else retrieved_at[:10]
                observation_id = _id("obs", source, source_ref, observed_at, "listing")
                is_current = observed_at == retrieved_at[:10]
                raw_fields = dict(listing) if is_current else {
                    "price": snapshot["price"], "lease_terms": snapshot["lease_terms"], "status": snapshot["status"],
                    "legacy_note": "Historical snapshot predates catalog source-document capture.",
                }
                self.conn.execute(
                    "INSERT INTO observations "
                    "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
                    "bedrooms,bathrooms,price,status,raw_fields,evidence_grade) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                    "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
                    "bedrooms=excluded.bedrooms,bathrooms=excluded.bathrooms,price=excluded.price,status=excluded.status,"
                    "raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
                    (observation_id, document_id if is_current else None, source, source_ref, observed_at,
                     "listing", listing["address"], listing["unit_number"], listing["bedrooms"],
                     listing["bathrooms"], snapshot["price"], snapshot["status"],
                     json.dumps(raw_fields, default=str, sort_keys=True),
                     "source_document" if is_current else "legacy_snapshot"),
                )
                self._match(observation_id, "building", bbl, match_status, confidence, method, rationale)
                self._record_bbl_candidates(observation_id, listing["address"], listing["zipcode"])
                if unit_id:
                    self._match(observation_id, "unit", unit_id, "resolved", 1.0,
                                "exact_bbl_and_normalized_unit",
                                "resolved building plus non-empty normalized unit label")
                    resolved += 1
                elif is_non_dwelling:
                    self._match(observation_id, "unit", None, "not_a_dwelling", 0.0,
                                "exact_bbl_and_normalized_unit", "listing unit label names a non-dwelling space")
                    unresolved += 1
                else:
                    unit_status = match_status if not bbl else "unresolved"
                    unit_reason = rationale if not bbl else "listing does not contain a usable unit label"
                    self._match(observation_id, "unit", None, unit_status, 0.0,
                                "exact_bbl_and_normalized_unit", unit_reason)
                    unresolved += 1
                observations += 1
        self.conn.commit()
        return {"listings": len(listings), "observations": observations, "units": units,
                "resolved_unit_observations": resolved, "unresolved_unit_observations": unresolved}

    def status(self):
        units = self.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        pluto_units = self.conn.execute("SELECT COALESCE(SUM(units_res), 0) FROM buildings").fetchone()[0]
        capacity_slots = self.conn.execute("SELECT COUNT(*) FROM housing_capacity_slots").fetchone()[0]
        return {
            "buildings": self.conn.execute("SELECT COUNT(*) FROM buildings").fetchone()[0],
            "addresses": self.conn.execute("SELECT COUNT(*) FROM addresses").fetchone()[0],
            "units": units,
            "addressable_units": self.conn.execute("SELECT COUNT(*) FROM addressable_units").fetchone()[0],
            "nyc_housing_stock_target": NYC_HOUSING_STOCK_TARGET,
            "evidenced_unit_coverage": units / NYC_HOUSING_STOCK_TARGET,
            "pluto_residential_unit_capacity": pluto_units,
            "evidenced_unit_coverage_against_pluto": units / pluto_units if pluto_units else 0,
            "anonymous_capacity_slots": capacity_slots,
            "official_unit_lots": self.conn.execute("SELECT COUNT(*) FROM official_unit_lots").fetchone()[0],
            "observations": self.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
            "resolved_unit_observations": self.conn.execute(
                "SELECT COUNT(*) FROM entity_matches WHERE entity_type='unit' AND status='resolved'"
            ).fetchone()[0],
            "unresolved_unit_observations": self.conn.execute(
                "SELECT COUNT(*) FROM entity_matches WHERE entity_type='unit' AND status!='resolved'"
            ).fetchone()[0],
        }

    def derive_addressable_units(self, limit=10000, batches=1):
        """Derive address-plus-unit identities from source observations.

        A source address must exactly match an imported PAD address on the resolved
        BBL. This intentionally leaves BBL-only observations at lot level when a
        tax lot contains multiple physical addresses.
        """
        if limit <= 0 or batches <= 0:
            raise ValueError("limit and batches must be positive")
        progress_source = "observation_addressable_units_v1"
        state = self.conn.execute(
            "SELECT cursor_rowid FROM addressable_unit_progress WHERE source=?", (progress_source,)
        ).fetchone()
        cursor = state[0] if state else 0
        scanned = derived = unresolved = 0
        for _ in range(batches):
            records = self.conn.execute(
                "SELECT o.rowid,o.observation_id,o.address,o.unit_label,b.entity_id "
                "FROM observations o JOIN entity_matches b ON b.observation_id=o.observation_id "
                "AND b.entity_type='building' AND b.status='resolved' AND b.entity_id IS NOT NULL "
                "WHERE o.rowid>? AND o.address IS NOT NULL AND o.unit_label IS NOT NULL "
                "ORDER BY o.rowid LIMIT ?",
                (cursor, limit),
            ).fetchall()
            if not records:
                break
            for rowid, observation_id, address, raw_label, bbl in records:
                cursor = rowid
                scanned += 1
                normalized_address = normalize_address(address)
                normalized_unit = normalize_unit(raw_label)
                if not normalized_address or not normalized_unit or str(raw_label).strip().upper() in NON_DWELLING_UNIT_LABELS:
                    unresolved += 1
                    continue
                official = self.conn.execute(
                    "SELECT address,zipcode FROM addresses WHERE bbl=? AND normalized=? AND source='nyc_pad'",
                    (bbl, normalized_address),
                ).fetchone()
                if not official:
                    unresolved += 1
                    continue
                premise_id = _id("premise", bbl, normalized_address)
                now = _now()
                self.conn.execute(
                    "INSERT INTO premises (premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                    (premise_id, bbl, official[0], normalized_address, official[1], "nyc_pad", now, now),
                )
                addressable_unit_id = _id("addressable_unit", premise_id, normalized_unit)
                self.conn.execute(
                    "INSERT INTO addressable_units "
                    "(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET "
                    "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
                    (addressable_unit_id, premise_id, raw_label, normalized_unit, now, now),
                )
                self._match(
                    observation_id, "addressable_unit", addressable_unit_id, "resolved", 1.0,
                    "exact_pad_address_and_unit_label",
                    "source address exactly matches PAD on the resolved BBL plus a usable unit label",
                )
                derived += 1
            self.conn.execute(
                "INSERT OR REPLACE INTO addressable_unit_progress (source,cursor_rowid,updated_at) VALUES (?,?,?)",
                (progress_source, cursor, _now()),
            )
            self.conn.commit()
            if len(records) < limit:
                break
        return {"addressable_observations_scanned": scanned, "addressable_units_derived": derived,
                "addressable_observations_unresolved": unresolved, "addressable_cursor_rowid": cursor}

    def capacity_gaps(self, limit=100, borough=None):
        """Return PLUTO capacity gaps without manufacturing missing unit identities."""
        if limit <= 0:
            raise ValueError("gap limit must be positive")
        where = "b.units_res > 0"
        params = []
        if borough:
            where += " AND b.borough=?"
            params.append(BOROUGHS[borough][1])
        params.append(limit)
        cursor = self.conn.execute(
            "WITH named AS (SELECT bbl, COUNT(*) AS named_units FROM units GROUP BY bbl) "
            "SELECT b.bbl,b.borough,b.primary_address AS address,b.zipcode,b.units_res,COALESCE(n.named_units,0) AS named_units,"
            "b.units_res-COALESCE(n.named_units,0) AS unnamed_capacity "
            "FROM buildings b LEFT JOIN named n ON n.bbl=b.bbl WHERE " + where + " "
            "ORDER BY unnamed_capacity DESC, b.units_res DESC, b.bbl LIMIT ?",
            params,
        )
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def materialize_capacity_slots(self, batch_size=1000, batches=1):
        """Materialize anonymous PLUTO-counted residential capacity positions.

        Slots preserve an official building-level cardinality claim. They never carry
        a unit label and must not be displayed or joined as a named apartment until
        independent primary material establishes an actual unit identity.
        """
        source = "nyc_pluto_residential_capacity"
        self._source(source, "public_record", "NYC PLUTO units_res building-level capacity")
        if batch_size <= 0 or batches <= 0:
            raise ValueError("batch_size and batches must be positive")
        generated_at = _now()
        slot_count = self.conn.execute("SELECT COALESCE(SUM(units_res),0) FROM buildings WHERE units_res > 0").fetchone()[0]
        source_ref = _id("pluto_capacity", slot_count, generated_at[:10])
        # This describes a deterministic PLUTO-derived cardinality, so retries and
        # resumptions must point to the same source document.
        document_id = _id("doc", source, source_ref)
        self.conn.execute(
            "INSERT OR IGNORE INTO source_documents "
            "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
            (document_id, source, source_ref, generated_at,
             json.dumps({"units_res_total": slot_count, "building_count": self.conn.execute("SELECT COUNT(*) FROM buildings WHERE units_res > 0").fetchone()[0]}, sort_keys=True),
             "derived_from_imported_primary_rows"),
        )
        state = self.conn.execute(
            "SELECT run_id,cursor_bbl,completed FROM capacity_slot_progress WHERE source=?", (source,)
        ).fetchone()
        run_id, cursor_bbl, completed = state if state else (_id("capacity_slots", source_ref), None, 0)
        processed = 0
        for _ in range(batches):
            if completed:
                break
            bbls = self.conn.execute(
                "SELECT bbl FROM buildings WHERE units_res > 0 AND (? IS NULL OR bbl > ?) "
                "ORDER BY bbl LIMIT ?", (cursor_bbl, cursor_bbl, batch_size)
            ).fetchall()
            if not bbls:
                completed = 1
                break
            first_bbl, last_bbl = bbls[0][0], bbls[-1][0]
            max_units = self.conn.execute(
                "SELECT COALESCE(MAX(units_res),0) FROM buildings WHERE bbl BETWEEN ? AND ?", (first_bbl, last_bbl)
            ).fetchone()[0]
            self.conn.execute(
                "WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM seq WHERE n < ?) "
                "INSERT INTO housing_capacity_slots (slot_id,bbl,slot_ordinal,run_id) "
                "SELECT 'capacity_' || b.bbl || '_' || seq.n, b.bbl, seq.n, ? "
                "FROM buildings b JOIN seq ON seq.n <= b.units_res WHERE b.bbl BETWEEN ? AND ? AND b.units_res > 0 "
                "ON CONFLICT(bbl,slot_ordinal) DO UPDATE SET run_id=excluded.run_id",
                (max_units, run_id, first_bbl, last_bbl),
            )
            cursor_bbl = last_bbl
            processed += len(bbls)
            self.conn.execute(
                "INSERT OR REPLACE INTO capacity_slot_progress (source,run_id,cursor_bbl,completed,updated_at) VALUES (?,?,?,?,?)",
                (source, run_id, cursor_bbl, 0, _now()),
            )
            self.conn.commit()
        self.conn.execute(
            "INSERT OR REPLACE INTO capacity_slot_progress (source,run_id,cursor_bbl,completed,updated_at) VALUES (?,?,?,?,?)",
            (source, run_id, cursor_bbl, completed, _now()),
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO capacity_slot_runs (run_id,source,source_document_id,slot_count,generated_at) VALUES (?,?,?,?,?)",
            (run_id, source, document_id, slot_count, generated_at),
        )
        self.conn.commit()
        materialized = self.conn.execute("SELECT COUNT(*) FROM housing_capacity_slots").fetchone()[0]
        return {"capacity_slot_run_id": run_id, "pluto_residential_capacity": slot_count,
                "anonymous_capacity_slots": materialized, "capacity_buildings_processed": processed,
                "capacity_cursor_bbl": cursor_bbl, "capacity_complete": bool(completed)}
