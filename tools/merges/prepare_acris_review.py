#!/usr/bin/env python3
"""Prepare a ranked review queue from deterministic ACRIS evidence."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    with open(args.evidence, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    unresolved = [row for row in rows if row["status"] != "unit_row"]
    unresolved.sort(
        key=lambda row: (
            -int(row["unresolved_capacity"] or 0),
            row["borough"],
            row["address"],
        )
    )
    fields = list(unresolved[0]) if unresolved else []
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(unresolved)

    status_counts = Counter(row["status"] for row in unresolved)
    borough_counts = Counter(row["borough"] for row in unresolved)
    class_counts = Counter(row["building_class"] for row in unresolved)
    summary = {
        "evidence_rows": len(rows),
        "unresolved_targets": len(unresolved),
        "status_counts": dict(sorted(status_counts.items())),
        "borough_counts": dict(sorted(borough_counts.items())),
        "building_class_counts": dict(sorted(class_counts.items())),
        "ordering": "unresolved_capacity descending, then borough and address",
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(unresolved)} unresolved targets to {output}")
    print(f"wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
