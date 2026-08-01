#!/usr/bin/env python3
"""Add the safe subset of two-family address-level dwellings.

This only uses lots where PLUTO reports exactly two residential units and PAD
reports exactly two distinct addresses on the same street. Each address is a
separate dwelling identity, but neither address is treated as an apartment
number. The method is deliberately narrower than using PAD address counts as
a general unit rule.
"""
import argparse
import re
import sqlite3
import time
import uuid

SOURCE = "pad_same_street_two_family"


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def stable_id(*parts):
    return uuid.uuid5(uuid.NAMESPACE_URL, "|".join(str(part) for part in parts)).hex[:20]


def split_address(value):
    match = re.match(r"^(\S+)\s+(.+)$", (value or "").strip())
    if not match or not re.fullmatch(r"\d+(?:-\d+)?[A-Za-z]?", match.group(1)):
        return None
    return (match.group(1), re.sub(r"\s+", " ", match.group(2)).strip().upper())


def main():
    parser = argparse.ArgumentParser(description="Merge the conservative PAD/PLUTO two-family subset.")
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(args.catalog_db)
    conn.execute("PRAGMA busy_timeout=30000")
    stamp = now()
    rows = conn.execute(
        """
        SELECT b.bbl, x.norm_address
        FROM buildings b
        JOIN crosswalk x ON x.bbl = b.bbl
        WHERE b.units_res = 2
        GROUP BY b.bbl, x.norm_address
        """
    ).fetchall()

    by_bbl = {}
    for bbl, address in rows:
        by_bbl.setdefault(bbl, []).append(address)
    targets = []
    for bbl, addresses in by_bbl.items():
        if len(addresses) != 2:
            continue
        parsed = [split_address(address) for address in addresses]
        if any(item is None for item in parsed) or parsed[0][1] != parsed[1][1]:
            continue
        targets.append((bbl, sorted(addresses)))

    existing = {
        (bbl, normalized)
        for bbl, normalized in conn.execute(
            "SELECT bbl, normalized_unit FROM units WHERE normalized_unit LIKE 'ADDRESS:%'"
        )
    }
    targets = [
        (bbl, [address for address in addresses if (bbl, "ADDRESS:" + address) not in existing])
        for bbl, addresses in targets
    ]
    targets = [(bbl, addresses) for bbl, addresses in targets if addresses]

    print(f"target buildings: {len(targets)}")
    print(f"target dwellings: {len(targets) * 2}")
    if args.dry_run:
        return

    conn.execute(
        "INSERT INTO sources (source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?) "
        "ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
        (SOURCE, "derived_inference", "PLUTO units_res=2 plus exactly two distinct PAD addresses on the same street; "
         "each address is retained as an address-level dwelling identity, never as an invented apartment label.", stamp, stamp),
    )
    units = []
    observations = []
    matches = []
    for bbl, addresses in targets:
        for address in addresses:
            normalized = "ADDRESS:" + address
            unit_id = stable_id("unit", SOURCE, bbl, address)
            observation_id = stable_id("obs", SOURCE, bbl, address)
            label = "(whole building: " + address + ")"
            units.append((unit_id, bbl, label, normalized, stamp, stamp))
            observations.append((observation_id, None, SOURCE, bbl + ":" + address, stamp,
                                 "address_level_dwelling", address, label, "derived_inference"))
            matches.extend([
                (observation_id, "building", bbl, "resolved", 1.0, "pluto_units_res_and_pad_same_street",
                 "PLUTO reports two residential units and PAD supplies exactly two same-street addresses", stamp),
                (observation_id, "unit", unit_id, "candidate", 0.8, "pad_address_level_dwelling_candidate",
                 "Address supports a dwelling candidate on a two-family lot; no apartment number was inferred", stamp),
            ])
    conn.executemany(
        "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(bbl,normalized_unit) DO NOTHING", units)
    conn.executemany(
        "INSERT INTO observations (observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,evidence_grade) "
        "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(source,source_ref,observed_at,observation_kind) DO NOTHING", observations)
    conn.executemany(
        "INSERT INTO entity_matches (observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO NOTHING", matches)
    conn.commit()
    print(f"merged dwellings: {len(units)}")


if __name__ == "__main__":
    main()
