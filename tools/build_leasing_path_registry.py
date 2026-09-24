#!/usr/bin/env python3
"""Flatten the manager registry into auditable public leasing-path rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


def page_label(page: dict) -> str:
    anchor = " ".join(str(page.get("anchor_text", "")).split())
    if anchor:
        return anchor
    path = urlparse(page.get("final_url") or page.get("url") or "").path.strip("/")
    if not path:
        return "official homepage"
    return path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")


def evidence_level(page: dict) -> str:
    if page.get("error"):
        return "public_link_unchecked"
    if page.get("page_kind") == "vendor_portal":
        return "public_vendor_portal"
    if page.get("vendor_hints"):
        return "public_page_vendor_hint"
    return "public_page"


def flatten(registry: list[dict]) -> list[dict]:
    rows = []
    for manager in registry:
        for page in manager.get("public_page_candidates", []):
            public_url = page.get("url")
            final_url = page.get("final_url") or public_url
            if not public_url:
                continue
            record_key = "|".join(
                [manager.get("manager_slug", ""), str(public_url), str(final_url)]
            )
            rows.append(
                {
                    "id": hashlib.sha256(record_key.encode()).hexdigest()[:16],
                    "manager_name": manager.get("manager_name"),
                    "manager_slug": manager.get("manager_slug"),
                    "manager_profile_url": manager.get("profile_url"),
                    "page_label": page_label(page),
                    "page_kind": page.get("page_kind"),
                    "public_url": public_url,
                    "final_url": final_url,
                    "source_page_url": page.get("source_url"),
                    "vendor_hints": sorted(set(page.get("vendor_hints", []))),
                    "evidence_level": evidence_level(page),
                    "http_status": page.get("http_status"),
                    "error": page.get("error"),
                    "checked_at": manager.get("checked_at"),
                    "evidence_urls": [
                        value
                        for value in dict.fromkeys(
                            [page.get("source_url"), public_url, final_url]
                        )
                        if value
                    ],
                }
            )
    return sorted(rows, key=lambda row: (row["manager_slug"], row["public_url"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Manager registry JSONL")
    parser.add_argument("--output", type=Path, required=True, help="Flat leasing-path JSONL")
    args = parser.parse_args(argv)

    registry = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = flatten(registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")
    print(f"wrote {len(rows)} leasing-path rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
