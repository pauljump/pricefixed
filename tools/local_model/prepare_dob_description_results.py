#!/usr/bin/env python3
"""Verify local-Qwen DOB-description results against deterministic evidence."""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels
from tools.merges.mine_dob_electrical_detail_units import extract_electrical_detail_labels


def normalize_unit(value):
    value = re.sub(r"\b(APT|APARTMENT|UNIT|NO)\b\.?", "", str(value or "").upper())
    value = re.sub(r"[^A-Z0-9]", "", value)
    return str(int(value)) if value.isdigit() else value


def normalize_text(value):
    return " ".join(str(value or "").upper().split())


def candidate_is_standalone(label, description, extractor=extract_explicit_unit_labels):
    """Require the deterministic source grammar to reproduce the candidate."""
    key = normalize_unit(label)
    return bool(key) and key in {
        normalize_unit(candidate) for candidate in extractor(description)
    }


def load_terminal_results(path):
    """Keep the latest usable result per id; transport errors never prove completion."""
    results = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            result = json.loads(line)
            if result.get("status") in {"ok", "invalid_json"}:
                results[result["id"]] = result
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packets", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--accepted", required=True)
    parser.add_argument("--rejected", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument(
        "--source-parser", choices=("default", "electrical_detail"), default="default"
    )
    args = parser.parse_args()
    extractor = (
        extract_electrical_detail_labels
        if args.source_parser == "electrical_detail" else extract_explicit_unit_labels
    )
    packets = {}
    with open(args.packets, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                packet = json.loads(line)
                packets[packet["id"]] = packet
    results = load_terminal_results(args.results)
    missing = sum(packet_id not in results for packet_id in packets)
    if missing:
        raise SystemExit(
            f"Qwen run incomplete: {len(packets) - missing}/{len(packets)} terminal results"
        )

    accepted = []
    rejected = []
    reasons = Counter()
    for packet_id, packet in packets.items():
        result = results.get(packet_id, {})
        parsed = result.get("parsed") or {}
        candidates = {normalize_unit(label): label for label in packet["candidate_labels"]}
        candidate_keys = set(candidates)
        description = normalize_text(packet["text"])
        model_labels = parsed.get("unit_labels") or []
        if result.get("status") != "ok" or parsed.get("confidence") not in {"high", "medium"}:
            reasons["model_not_usable"] += 1
            rejected.append({"id": packet_id, "reason": "model_not_usable"})
            continue
        kept = 0
        for item in model_labels:
            label = str(item.get("label") or "").strip()
            evidence = normalize_text(item.get("evidence"))
            key = normalize_unit(label)
            reason = ""
            if not key or key not in candidate_keys:
                reason = "label_not_in_deterministic_candidates"
            elif not candidate_is_standalone(candidates[key], packet["text"], extractor):
                reason = "candidate_is_partial_token"
            elif not evidence or evidence not in description:
                reason = "evidence_not_in_source_description"
            if reason:
                reasons[reason] += 1
                continue
            accepted.append({
                "bbl": packet["bbl"], "address": packet["target_address"],
                "unit_label": label,
                "source_ref": packet.get("source_ref", packet_id.removeprefix("dob-description-")),
                "source_url": packet["source_url"], "observed_at": packet.get("observed_at", ""),
                "evidence": item.get("evidence", ""), "confidence": parsed["confidence"],
            })
            kept += 1
        if not kept:
            reasons["no_verified_unit_label"] += 1
            rejected.append({"id": packet_id, "reason": "no_verified_unit_label"})

    accepted_path = Path(args.accepted)
    accepted_path.parent.mkdir(parents=True, exist_ok=True)
    with accepted_path.open("w", encoding="utf-8", newline="") as handle:
        fields = ("bbl", "address", "unit_label", "source_ref", "source_url",
                  "observed_at", "evidence", "confidence")
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(accepted)
    with Path(args.rejected).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("id", "reason"))
        writer.writeheader()
        writer.writerows(rejected)
    summary = {
        "packets": len(packets), "results": len(results),
        "accepted_unit_labels": len(accepted), "rejected_packets": len(rejected),
        "rejection_reasons": dict(sorted(reasons.items())), "catalog_writes": 0,
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
