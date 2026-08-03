#!/usr/bin/env python3
"""Prepare deduplicated, net-new unit candidates from compact public mentions."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.catalog.core import NON_DWELLING_UNIT_LABELS
from pricefixed.engine.dedupe import normalize_unit


SOURCE_PRIORITY = ("dob_jobs", "dob_permits", "hpd_problems", "hpd_violations", "hpd_omo",
                   "nycha_violations", "evictions")


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
            label_key = str(label or "").strip().upper()
            normalized = normalize_unit(label)
            if (not normalized or label_key in NON_DWELLING_UNIT_LABELS or
                    label_key in {"ALL", "N/A", "NA"}):
                rejected += 1
                continue
            batch.append((bbl, normalized, label, address, zipcode, source, source_ref,
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
