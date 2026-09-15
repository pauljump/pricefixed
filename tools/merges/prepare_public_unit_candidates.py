#!/usr/bin/env python3
"""Prepare deduplicated, net-new unit candidates from compact public mentions."""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.catalog.core import NON_DWELLING_UNIT_LABELS
from pricefixed.engine.dedupe import normalize_unit


SOURCE_PRIORITY = ("dob_jobs", "dob_permits", "hpd_problems", "hpd_violations", "hpd_omo",
                   "nycha_violations", "evictions")

_LOCATION_WORDS = re.compile(
    r"\b(?:ATTIC|BACK|BASEM?E?N?T?|BSM?T|BUILDING|CELLAR|COMMERCIAL|ENTIRE|FIRST|"
    r"FLOOR|FLR|GROUND|HOUSE|LOBBY|OFFICE|PARKING|PRIVATE|REAR|RETAIL|ROOF|"
    r"SECOND|SIDE|STORAGE|STORE|TOP)\b"
)
_LOCATION_CODES = re.compile(
    r"^(?:NONE|OSP|PVT|PRIVAT|APARTM|HOUSE|ATTIC|BACK|SIDE|REAR|GROUND|GROUN|GRND|"
    r"GRD|TOP|STORE|COMMERCIAL|PARKING|ENTIRE|FIRST|SECOND|BASE|BASEM|BASEME|"
    r"BAS|BASMT|BSM|BSMT|BSMNT|BMT|BST|BM|0)$"
)
_FLOOR_CODE = re.compile(
    r"^(?:(?:\d+)(?:ST|ND|RD|TH)?(?:FL|FLO|FLOO|FLOOR|FLR|F)|"
    r"(?:FL|FLOOR|FLR)\d+|(?:FIRST|SECOND|THIRD|FOURTH)|(?:1ST|2ND|3RD|\d+TH))$"
)
_UNIT_CODE = re.compile(r"^(?:\d{1,4}[A-Z]{0,3}|[A-Z]{1,3}\d{1,4}|PH[A-Z0-9]{0,3})$")


def usable_dwelling_label(source, label, allow_delimiters=False):
    """Accept only one compact apartment identifier from an official unit field.

    The raw mentions remain in the evidence database. Ambiguous floor, commercial,
    common-area, and multi-unit strings are withheld rather than counted as homes.
    """
    raw = " ".join(str(label or "").strip().upper().split())
    normalized = normalize_unit(raw)
    if (not normalized or raw in NON_DWELLING_UNIT_LABELS or raw in {"ALL", "N/A", "NA"} or
            _LOCATION_WORDS.search(raw) or _LOCATION_CODES.fullmatch(normalized) or
            _FLOOR_CODE.fullmatch(normalized)):
        return None
    # Delimiters in DOB and eviction fields usually join several premises. The
    # compact pass must not collapse them into a made-up combined unit label.
    if (not allow_delimiters and source in {"dob_jobs", "dob_permits", "evictions"} and
            re.search(r"[,/&;]", raw)):
        return None
    if not _UNIT_CODE.fullmatch(normalized):
        return None
    return normalized


def usable_dwelling_labels(source, label):
    """Return normalized/raw label pairs, splitting only DOB's plural unit field."""
    raw = " ".join(str(label or "").strip().upper().split())
    if source in {"dob_jobs", "dob_permits"} and re.search(r"[,/&;]", raw):
        parts = [part.strip() for part in re.split(r"\s*[,/&;]\s*", raw) if part.strip()]
        if len(parts) < 2:
            return []
        labels = []
        for part in parts:
            normalized = usable_dwelling_label(source, part, allow_delimiters=True)
            if not normalized:
                return []
            labels.append((normalized, part))
        return list(dict.fromkeys(labels))
    normalized = usable_dwelling_label(source, raw)
    return [(normalized, raw)] if normalized else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mentions-db", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    conn = sqlite3.connect(args.mentions_db)
    conn.execute("PRAGMA journal_mode=WAL")
    progress = dict(conn.execute("SELECT source,complete FROM progress").fetchall())
    incomplete = [source for source in SOURCE_PRIORITY if progress.get(source) != 1]
    if incomplete:
        raise SystemExit("source mining is incomplete: " + ", ".join(incomplete))
    conn.executescript("""
        DROP TABLE IF EXISTS unit_candidates;
        CREATE TABLE unit_candidates (
            bbl TEXT NOT NULL, normalized_unit TEXT NOT NULL, unit_label TEXT NOT NULL,
            address TEXT NOT NULL, zipcode TEXT, source TEXT NOT NULL, source_ref TEXT NOT NULL,
            observed_at TEXT, dataset TEXT NOT NULL, source_url TEXT NOT NULL,
            exists_in_catalog INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(bbl,normalized_unit)
        );
    """)
    rejected = 0
    for source in SOURCE_PRIORITY:
        rows = conn.execute(
            "SELECT bbl,address,zipcode,unit_label,source_ref,observed_at,dataset,source_url "
            "FROM mentions WHERE source=? ORDER BY rowid", (source,)
        )
        batch = []
        for bbl, address, zipcode, label, source_ref, observed_at, dataset, source_url in rows:
            labels = usable_dwelling_labels(source, label)
            if not labels:
                rejected += 1
                continue
            for normalized, candidate_label in labels:
                batch.append((bbl, normalized, candidate_label, address, zipcode, source, source_ref,
                              observed_at, dataset, source_url))
                if len(batch) >= 20000:
                    conn.executemany(
                        "INSERT OR IGNORE INTO unit_candidates "
                        "(bbl,normalized_unit,unit_label,address,zipcode,source,source_ref,observed_at,dataset,source_url) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)", batch,
                    )
                    conn.commit()
                    batch = []
        if batch:
            conn.executemany(
                "INSERT OR IGNORE INTO unit_candidates "
                "(bbl,normalized_unit,unit_label,address,zipcode,source,source_ref,observed_at,dataset,source_url) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)", batch,
            )
            conn.commit()

    catalog_uri = f"file:{Path(args.catalog_db).resolve()}?mode=ro"
    conn.execute("ATTACH DATABASE ? AS catalog", (catalog_uri,))
    conn.execute(
        "UPDATE unit_candidates SET exists_in_catalog=EXISTS("
        "SELECT 1 FROM catalog.units u WHERE u.bbl=unit_candidates.bbl "
        "AND u.normalized_unit=unit_candidates.normalized_unit)"
    )
    conn.commit()
    summary = {
        "candidate_units": conn.execute("SELECT COUNT(*) FROM unit_candidates").fetchone()[0],
        "net_new_units": conn.execute("SELECT COUNT(*) FROM unit_candidates WHERE exists_in_catalog=0").fetchone()[0],
        "already_in_catalog": conn.execute("SELECT COUNT(*) FROM unit_candidates WHERE exists_in_catalog=1").fetchone()[0],
        "rejected_non_dwelling_or_empty_mentions": rejected,
        "net_new_by_source": dict(conn.execute(
            "SELECT source,COUNT(*) FROM unit_candidates WHERE exists_in_catalog=0 GROUP BY source ORDER BY source"
        ).fetchall()),
        "catalog_writes": 0,
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
