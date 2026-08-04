#!/usr/bin/env python3
"""Count apartment markers in NYC datasets with text and building fields."""
import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.merges.audit_nyc_open_data_fields import BUILDING_FIELDS, TEXT_FIELD


def text_fields(dataset):
    types = dataset.get("types") or {}
    return [
        field for field in dataset.get("fields", [])
        if TEXT_FIELD.search(field) and (not types or types.get(field) == "Text")
    ]


def marker_where(dataset, fields):
    identities = sorted(set(dataset.get("fields", [])) & BUILDING_FIELDS)
    identity = " OR ".join(f"{field} is not null" for field in identities)
    markers = []
    for field in fields:
        markers.extend((
            f"upper({field}) like 'APT%'",
            f"upper({field}) like '% APT%'",
            f"upper({field}) like '%(APT%'",
            f"upper({field}) like '%/APT%'",
            f"upper({field}) like '%APARTMENT%'",
            f"upper({field}) like '%DWELLING UNIT%'",
            f"upper({field}) like '%RESIDENTIAL UNIT%'",
        ))
    return f"({identity}) AND ({' OR '.join(markers)})"


def query_count(dataset, fields):
    params = urlencode({
        "$select": "count(*) as rows", "$where": marker_where(dataset, fields),
    })
    request = Request(
        f"https://data.cityofnewyork.us/resource/{dataset['id']}.json?{params}",
        headers={"User-Agent": "pricefixed-public-records/1.0"},
    )
    for attempt in range(5):
        try:
            with urlopen(request, timeout=180) as response:
                rows = json.loads(response.read())
                return int(rows[0]["rows"])
        except HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            if attempt == 4:
                raise
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable marker query retry state")


def load_completed(path):
    if not path.is_file():
        return set()
    completed = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                completed.add(json.loads(line)["dataset"])
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    datasets = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = load_completed(output)
    candidates = [
        dataset for dataset in datasets
        if set(dataset.get("fields", [])) & BUILDING_FIELDS and text_fields(dataset)
    ]
    with output.open("a", encoding="utf-8") as handle:
        for index, dataset in enumerate(candidates, 1):
            if dataset["id"] in completed:
                continue
            fields = text_fields(dataset)
            result = {
                "dataset": dataset["id"], "name": dataset["name"],
                "building_fields": sorted(set(dataset["fields"]) & BUILDING_FIELDS),
                "text_fields": fields,
            }
            try:
                result.update(status="ok", rows=query_count(dataset, fields))
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
                result.update(status="error", error=f"{type(exc).__name__}: {exc}")
            handle.write(json.dumps(result, ensure_ascii=True) + "\n")
            handle.flush()
            print(
                f"marker audit {index}/{len(candidates)} {dataset['id']} "
                f"status={result['status']} rows={result.get('rows', 0)}",
                flush=True,
            )


if __name__ == "__main__":
    main()
