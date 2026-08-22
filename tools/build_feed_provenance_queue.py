#!/usr/bin/env python3
"""Build a manager-level queue for investigating hidden listing transports."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _paths_by_manager(paths: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for path in paths:
        grouped.setdefault(path.get("manager_slug", ""), []).append(path)
    return grouped


def _priority(manager: dict, paths: list[dict]) -> str:
    buildings = manager.get("buildings_managed") or 0
    rentals = manager.get("managed_rentals") or 0
    vendor_portals = sum(path.get("evidence_level") == "public_vendor_portal" for path in paths)
    successful = sum(not path.get("error") for path in paths)
    if (buildings >= 50 or rentals >= 50) and not successful:
        return "high"
    if vendor_portals or (buildings >= 20 and successful):
        return "high"
    if successful or buildings >= 10 or rentals >= 10:
        return "medium"
    return "low"


def _hypotheses(manager: dict, paths: list[dict]) -> list[str]:
    hypotheses = []
    successful = [path for path in paths if not path.get("error")]
    vendor_portals = [path for path in paths if path.get("evidence_level") == "public_vendor_portal"]
    if manager.get("managed_rentals") and not successful:
        hypotheses.append("nybits_private_or_manual_transport_possible")
    if vendor_portals:
        hypotheses.append("public_vendor_path_may_be_upstream_of_nybits")
    if successful and not vendor_portals:
        hypotheses.append("custom_or_page_based_transport_possible")
    if manager.get("profile_error") or manager.get("website_status") == "fetch_error":
        hypotheses.append("official_site_unresolved")
    if not hypotheses:
        hypotheses.append("nybits_transport_unknown")
    return hypotheses


def _next_action(manager: dict, paths: list[dict]) -> str:
    if not paths:
        return "compare_nybits_rows_or_public_archives_before_guessing_endpoint"
    if any(path.get("evidence_level") == "public_vendor_portal" for path in paths):
        return "compare_nybits_rows_to_vendor_fields_and_ids"
    if any(path.get("error") for path in paths):
        return "recheck_failed_public_paths_and_preserve_response_evidence"
    return "compare_nybits_rows_to_manager_pages_and_public_listing_fields"


def build_queue(managers: list[dict], paths: list[dict]) -> list[dict]:
    grouped = _paths_by_manager(paths)
    rows = []
    for manager in managers:
        manager_paths = grouped.get(manager.get("manager_slug", ""), [])
        vendors = sorted({vendor for path in manager_paths for vendor in path.get("vendor_hints", [])})
        successful = [path for path in manager_paths if not path.get("error")]
        vendor_portals = [path for path in manager_paths if path.get("evidence_level") == "public_vendor_portal"]
        evidence_urls = list(
            dict.fromkeys(
                [
                    manager.get("profile_url"),
                    manager.get("official_website_url"),
                    *(url for path in manager_paths for url in path.get("evidence_urls", [])),
                ]
            )
        )
        row = {
            "manager_slug": manager.get("manager_slug"),
            "manager_name": manager.get("manager_name"),
            "nybits_profile_url": manager.get("profile_url"),
            "buildings_managed": manager.get("buildings_managed"),
            "managed_rentals": manager.get("managed_rentals"),
            "official_website_url": manager.get("official_website_url"),
            "public_path_count": len(manager_paths),
            "successful_public_path_count": len(successful),
            "public_vendor_portal_count": len(vendor_portals),
            "vendor_families": vendors,
            "nybits_transport_status": "unknown",
            "investigation_priority": _priority(manager, manager_paths),
            "hypotheses": _hypotheses(manager, manager_paths),
            "next_action": _next_action(manager, manager_paths),
            "evidence_urls": evidence_urls,
        }
        rows.append(row)
    priority = {"high": 0, "medium": 1, "low": 2}
    return sorted(rows, key=lambda row: (priority[row["investigation_priority"]], row["manager_name"].lower()))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--managers", type=Path, required=True, help="Manager registry JSONL")
    parser.add_argument("--paths", type=Path, required=True, help="Flat public leasing-path JSONL")
    parser.add_argument("--output", type=Path, required=True, help="Provenance queue JSONL")
    args = parser.parse_args(argv)
    managers = [json.loads(line) for line in args.managers.read_text(encoding="utf-8").splitlines() if line.strip()]
    paths = [json.loads(line) for line in args.paths.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = build_queue(managers, paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")
    print(f"wrote {len(rows)} provenance rows to {args.output}")
    print("priority counts:", dict(Counter(row["investigation_priority"] for row in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
