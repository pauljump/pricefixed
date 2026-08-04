#!/usr/bin/env python3
"""Inventory NYC Open Data fields that may contain unit-level housing evidence."""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CATALOG_API = "https://api.us.socrata.com/api/catalog/v1"
UNIT_FIELD = re.compile(r"(^|_)(apt|apartment|suite|unit|dwelling)(_|$)", re.I)
TEXT_FIELD = re.compile(
    r"(description|_desc$|^desc|comment|remark|note|detail|narrative|scope|summary|"
    r"descriptionofwork|work_reported|workscope)",
    re.I,
)
BUILDING_FIELDS = {
    "bbl", "borough_block_lot", "address_bbl", "gis_bbl",
    "nyc_borough_block_and_lot", "bin", "building_id", "buildingid",
    "hpd_building_id",
}


def query_catalog(offset, limit):
    params = urlencode({
        "search_context": "data.cityofnewyork.us", "only": "datasets",
        "limit": limit, "offset": offset,
    })
    request = Request(
        f"{CATALOG_API}?{params}",
        headers={"User-Agent": "pricefixed-public-records/1.0"},
    )
    for attempt in range(5):
        try:
            with urlopen(request, timeout=180) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            if attempt == 4:
                raise
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable catalog retry state")


def normalize_result(item):
    resource = item.get("resource") or {}
    classification = item.get("classification") or {}
    fields = resource.get("columns_field_name") or []
    datatypes = resource.get("columns_datatype") or []
    return {
        "id": str(resource.get("id") or ""),
        "name": str(resource.get("name") or ""),
        "description": str(resource.get("description") or ""),
        "category": str(classification.get("domain_category") or ""),
        "columns": resource.get("columns_name") or [],
        "fields": fields,
        "types": {
            field: datatype for field, datatype in zip(fields, datatypes)
        },
        "updatedAt": str(resource.get("updatedAt") or ""),
    }


def candidate_rows(datasets, matcher):
    rows = []
    for dataset in datasets:
        fields = [field for field in dataset["fields"] if matcher.search(field)]
        if fields:
            identity = sorted(set(dataset["fields"]) & BUILDING_FIELDS)
            rows.append((dataset["id"], dataset["name"], ",".join(identity), ",".join(fields)))
    return rows


def write_tsv(path, rows):
    path.write_text(
        "dataset\tname\tbuilding_fields\tcandidate_fields\n" +
        "".join("\t".join(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--page-size", type=int, default=1000)
    args = parser.parse_args()
    if args.page_size <= 0:
        raise SystemExit("--page-size must be positive")
    datasets = []
    offset = 0
    while True:
        page = query_catalog(offset, args.page_size)
        results = page.get("results") or []
        datasets.extend(normalize_result(item) for item in results)
        offset += len(results)
        total = int(page.get("resultSetSize") or offset)
        print(f"catalog offset={offset} total={total}", flush=True)
        if not results or offset >= total:
            break
    datasets = sorted(
        (dataset for dataset in datasets if dataset["id"]),
        key=lambda dataset: (dataset["name"].casefold(), dataset["id"]),
    )
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "nyc-datasets.json").write_text(
        json.dumps(datasets, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    write_tsv(out / "unit-field-candidates.tsv", candidate_rows(datasets, UNIT_FIELD))
    write_tsv(out / "description-field-candidates.tsv", candidate_rows(datasets, TEXT_FIELD))
    print(f"wrote {len(datasets)} NYC dataset schemas to {out}")


if __name__ == "__main__":
    main()
