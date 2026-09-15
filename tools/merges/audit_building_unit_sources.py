#!/usr/bin/env python3
"""Audit source packets for a building-level unit roster without writing a catalog."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit
from pricefixed.engine.identifiers import normalize_bbl
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels
from tools.merges.mine_dob_electrical_detail_units import extract_electrical_detail_labels


def expected_roster(floors=14, letters="ABCDEFGH", main_prefix="0M"):
    labels = [f"{floor:02d}{letter}" for floor in range(1, floors + 1) for letter in letters]
    return labels + [f"{main_prefix}{letter}" for letter in letters]


def _parser_for(packet):
    source_type = str(packet.get("source_type") or "").lower()
    return extract_electrical_detail_labels if "electrical_detail" in source_type else extract_explicit_unit_labels


def _roster_keys(label):
    normalized = normalize_unit(label)
    if not normalized:
        return set()
    keys = {normalized}
    if normalized[:1] == "0" and len(normalized) > 1 and normalized[1].isdigit():
        keys.add(normalized[1:])
    return keys


def _coerce_packet(raw):
    """Map approved-permit records into the packet fields used by the audit."""
    packet = dict(raw)
    if not packet.get("target_address") and packet.get("house_no") and packet.get("street_name"):
        packet["target_address"] = f'{packet["house_no"]} {packet["street_name"]}'
    if not packet.get("text"):
        packet["text"] = packet.get("job_description") or ""
    if not packet.get("source_type"):
        packet["source_type"] = "dob_approved_permit_description"
    if not packet.get("source_ref"):
        packet["source_ref"] = packet.get("job_filing_number") or packet.get("id")
    return packet


def _iter_packets(path):
    """Yield packet dictionaries from JSONL or approved-permit JSON exports."""
    path = Path(path)
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if line.strip():
                    yield line_number, _coerce_packet(json.loads(line))
        return

    try:
        with path.open(encoding="utf-8") as handle:
            records = json.load(handle)
    except json.JSONDecodeError:
        # approved-permit-25000.json is one object per line with a leading
        # comma after the first record, despite its .json extension.
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                line = line.strip()
                if line.startswith("["):
                    line = line[1:]
                if line.startswith(","):
                    line = line[1:]
                if line.endswith("]"):
                    line = line[:-1]
                if line:
                    yield line_number, _coerce_packet(json.loads(line))
        return

    if not isinstance(records, list):
        raise ValueError(f"Expected a JSON array in {path}")
    for line_number, record in enumerate(records, 1):
        yield line_number, _coerce_packet(record)


def audit_packets(paths, target_bbl, target_address, roster=None):
    target_address = normalize_address(target_address)
    hits = []
    observed = {"exact_address": set(), "shared_bbl": set()}
    repairs = []
    malformed_bbls = []
    roster = roster or expected_roster()
    roster_by_key = {key: label for label in roster for key in _roster_keys(label)}

    for path in paths:
        for line_number, packet in _iter_packets(path):
            raw_bbl = str(packet.get("bbl") or "")
            packet_bbl = normalize_bbl(raw_bbl)
            packet_address = normalize_address(packet.get("target_address") or "")
            exact_address = packet_address == target_address
            shared_bbl = packet_bbl == target_bbl
            if not exact_address and not shared_bbl:
                continue
            parser = _parser_for(packet)
            parsed = list(dict.fromkeys(parser(packet.get("text") or "")))
            stored = list(dict.fromkeys(str(label).upper() for label in packet.get("candidate_labels") or []))
            parsed_keys = {key for label in parsed for key in _roster_keys(label)}
            for key in parsed_keys:
                if key in roster_by_key:
                    observed["exact_address" if exact_address else "shared_bbl"].add(roster_by_key[key])
            if set(stored) != set(parsed):
                repairs.append({
                    "file": str(path), "line": line_number,
                    "source_ref": packet.get("source_ref") or packet.get("id"),
                    "stored_labels": stored, "reparsed_labels": parsed,
                })
            if raw_bbl and packet_bbl and raw_bbl != packet_bbl:
                malformed_bbls.append({
                    "file": str(path), "line": line_number,
                    "source_ref": packet.get("source_ref") or packet.get("id"),
                    "literal_bbl": raw_bbl, "normalized_bbl": packet_bbl,
                })
            hits.append({
                "file": str(path), "line": line_number,
                "source_ref": packet.get("source_ref") or packet.get("id"),
                "target_address": packet.get("target_address"),
                "literal_bbl": raw_bbl, "normalized_bbl": packet_bbl,
                "scope": "exact_address" if exact_address else "shared_bbl",
                "text": packet.get("text") or "",
                "stored_candidate_labels": stored,
                "reparsed_candidate_labels": parsed,
            })

    exact = observed["exact_address"]
    shared = observed["shared_bbl"]
    found = exact | shared
    return {
        "target_bbl": target_bbl,
        "target_address": target_address,
        "expected_units": len(roster),
        "exact_address_labels": sorted(exact),
        "shared_bbl_labels_only": sorted(shared - exact),
        "found_under_equivalent_labeling": sorted(found),
        "missing_from_scanned_sources": sorted(set(roster) - found),
        "packet_hits": hits,
        "parser_repairs": repairs,
        "malformed_bbls_repaired": malformed_bbls,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbl", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--packets", action="append", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    target_bbl = normalize_bbl(args.bbl)
    if not target_bbl:
        raise SystemExit("--bbl must be a valid NYC BBL")
    report = audit_packets(args.packets, target_bbl, args.address)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
