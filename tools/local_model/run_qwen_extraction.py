#!/usr/bin/env python3
"""Run audited, serial extraction against the local Qwen OpenAI-compatible server.

Input is JSONL with one document per line. Each record must contain ``id`` and
``text`` and may include ``source_url``, ``source_type``, and ``target_address``.
The output is JSONL and is resumable by record id. This script never calls a
cloud API and never writes to the canonical catalog.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://100.78.191.106:8080/v1"
DEFAULT_MODEL = "mlx-community/Qwen3-14B-4bit"
SYSTEM_PROMPT = """You extract housing facts from public-record document text.
Return JSON only. Never guess or complete missing facts.
Only report an address or unit label when the supplied text supports it.
An equipment, HVAC, electrical, plumbing, elevator, or construction "unit" is not
a home. Never return those as apartment labels.
Keep evidence as short verbatim snippets from the supplied text.
Use this schema exactly:
{
  "building_address": string or null,
  "unit_labels": [{"label": string, "evidence": string, "page": number or null}],
  "residential_count": number or null,
  "confidence": "high" or "medium" or "low",
  "notes": string
}
"""


def parse_json(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    labels = value.get("unit_labels")
    if not isinstance(labels, list):
        return None
    for item in labels:
        if not isinstance(item, dict) or not isinstance(item.get("label"), str):
            return None
    if value.get("building_address") is not None and not isinstance(value["building_address"], str):
        return None
    if value.get("residential_count") is not None and not isinstance(value["residential_count"], (int, float)):
        return None
    if value.get("confidence") not in {"high", "medium", "low"}:
        return None
    return value


def call_model(base_url, model, record, max_tokens, temperature, timeout):
    context = {
        "source_type": record.get("source_type"),
        "target_address": record.get("target_address"),
        "source_url": record.get("source_url"),
        "document_text": record["text"],
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    request = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read())
    content = result["choices"][0]["message"]["content"]
    return content, parse_json(content)


def cache_key(record):
    """Fields that determine extraction; filing URLs do not change the text facts."""
    return (
        record.get("source_type"), record.get("target_address"), record.get("text"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Input JSONL document packets")
    parser.add_argument("--output", required=True, help="Resumable output JSONL")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if args.max_tokens <= 0 or not 0 <= args.temperature <= 2:
        parser.error("max-tokens must be positive and temperature must be between 0 and 2")

    records = []
    records_by_id = {}
    with open(args.input, encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not record.get("id") or not record.get("text"):
                print(f"skip line {line_number}: id and text are required", file=sys.stderr)
                continue
            records.append(record)
            records_by_id[record["id"]] = record

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    cached = {}
    if output.exists():
        with output.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    result = json.loads(line)
                    completed.add(result["id"])
                    record = records_by_id.get(result["id"])
                    if record and result.get("status") == "ok":
                        cached[cache_key(record)] = result

    with output.open("a", encoding="utf-8") as sink:
        for record in records:
            if record["id"] in completed:
                continue
            result = {
                "id": record["id"],
                "source_url": record.get("source_url", ""),
                "model": args.model,
                "base_url": args.base_url,
            }
            prior = cached.get(cache_key(record))
            if prior:
                result.update({
                    "status": "ok", "parsed": prior["parsed"], "raw": prior.get("raw", ""),
                    "reused_from": prior["id"],
                })
            else:
                try:
                    raw, parsed = call_model(
                        args.base_url, args.model, record, args.max_tokens,
                        args.temperature, args.timeout
                    )
                    result.update({"status": "ok" if parsed else "invalid_json", "parsed": parsed, "raw": raw})
                except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                    result.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
            sink.write(json.dumps(result, ensure_ascii=True) + "\n")
            sink.flush()
            completed.add(record["id"])
            if result.get("status") == "ok":
                cached[cache_key(record)] = result
            print(f"processed {record['id']}", flush=True)


if __name__ == "__main__":
    main()
