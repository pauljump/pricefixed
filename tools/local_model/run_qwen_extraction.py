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
import time
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
BATCH_SYSTEM_PROMPT = """You verify apartment labels in short public-record descriptions.
For every input record, return one JSON array item with exactly this shape:
{"id":"exact input id","unit_labels":[{"label":"exact candidate label","evidence":"short exact substring from text"}],"confidence":"high|medium|low"}
Include a candidate only when the text clearly uses it as a residential apartment or
condo identifier. Exclude equipment, HVAC, plumbing, electrical, elevator,
construction, floor, room, job, and application numbers. Never invent a label or
evidence. Return JSON only, with one item per input record in input order.
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


def parse_batch_json(text, expected_ids):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(value, list) or len(value) != len(expected_ids):
        return None
    parsed = {}
    for item in value:
        if not isinstance(item, dict) or item.get("id") not in expected_ids:
            return None
        if item["id"] in parsed or item.get("confidence") not in {"high", "medium", "low"}:
            return None
        labels = item.get("unit_labels")
        if not isinstance(labels, list):
            return None
        if any(
            not isinstance(label, dict)
            or not isinstance(label.get("label"), str)
            or not isinstance(label.get("evidence"), str)
            for label in labels
        ):
            return None
        parsed[item["id"]] = item
    return parsed if set(parsed) == set(expected_ids) else None


def call_model_batch(base_url, model, records, max_tokens, temperature, timeout):
    contexts = [{
        "id": record["id"],
        "source_type": record.get("source_type"),
        "target_address": record.get("target_address"),
        "source_url": record.get("source_url"),
        "candidate_labels": record.get("candidate_labels", []),
        "text": record["text"],
    } for record in records]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": BATCH_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(contexts, ensure_ascii=True)},
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
    parsed = parse_batch_json(content, [record["id"] for record in records])
    if parsed is None:
        raise KeyError("local model returned an invalid or incomplete batch")
    return content, parsed


def standardize_batch_item(item, record):
    return {
        "building_address": record.get("target_address") or None,
        "unit_labels": [dict(label, page=None) for label in item["unit_labels"]],
        "residential_count": None,
        "confidence": item["confidence"],
        "notes": "Batched local-model verification of deterministic candidates.",
    }


def cache_key(record):
    """Fields that determine extraction; filing URLs do not change the text facts."""
    return (
        record.get("source_type"), record.get("target_address"), record.get("text"),
        tuple(record.get("candidate_labels") or ()),
    )


def load_existing_results(output, records_by_id):
    """Resume terminal results while leaving transport failures retryable."""
    completed = set()
    cached = {}
    if not output.exists():
        return completed, cached
    with output.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            result = json.loads(line)
            if result.get("status") not in {"ok", "invalid_json"}:
                continue
            completed.add(result["id"])
            record = records_by_id.get(result["id"])
            if record and result.get("status") == "ok":
                cached[cache_key(record)] = result
    return completed, cached


def call_with_retries(call, attempts, delay):
    """Retry server/transport failures, then stop without consuming the record."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            # Repeating the same malformed batch is rarely useful. Give Qwen one
            # retry, then let the caller split that batch into smaller requests.
            invalid_batch = isinstance(exc, KeyError)
            if attempt == attempts or (invalid_batch and attempt >= 2):
                raise RuntimeError(
                    f"local model unavailable after {attempts} attempts; "
                    "queue stopped without consuming the current record"
                ) from exc
            wait = delay * attempt
            print(
                f"local model call failed ({type(exc).__name__}: {exc}); "
                f"retrying in {wait}s ({attempt}/{attempts})",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(wait)


def extract_batch_with_fallback(args, records):
    """Extract one serial batch, splitting malformed responses until they parse."""
    if len(records) == 1:
        record = records[0]
        raw, parsed = call_with_retries(
            lambda: call_model(
                args.base_url, args.model, record, args.max_tokens,
                args.temperature, args.timeout,
            ),
            args.retry_attempts, args.retry_delay,
        )
        return {cache_key(record): (raw, parsed)}
    try:
        raw, parsed_items = call_with_retries(
            lambda: call_model_batch(
                args.base_url, args.model, records, args.max_tokens,
                args.temperature, args.timeout,
            ),
            args.retry_attempts, args.retry_delay,
        )
    except RuntimeError as exc:
        if not isinstance(exc.__cause__, KeyError):
            raise
        midpoint = len(records) // 2
        results = extract_batch_with_fallback(args, records[:midpoint])
        results.update(extract_batch_with_fallback(args, records[midpoint:]))
        return results
    return {
        cache_key(record): (
            json.dumps(parsed_items[record["id"]], ensure_ascii=True),
            standardize_batch_item(parsed_items[record["id"]], record),
        )
        for record in records
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Input JSONL document packets")
    parser.add_argument("--output", required=True, help="Resumable output JSONL")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retry-attempts", type=int, default=5)
    parser.add_argument("--retry-delay", type=float, default=15)
    parser.add_argument(
        "--batch-size", type=int, default=1,
        help="Records per serial request; use 8 for short deterministic candidate packets",
    )
    args = parser.parse_args()
    if args.max_tokens <= 0 or not 0 <= args.temperature <= 2:
        parser.error("max-tokens must be positive and temperature must be between 0 and 2")
    if args.retry_attempts <= 0 or args.retry_delay < 0:
        parser.error("retry-attempts must be positive and retry-delay must be non-negative")
    if args.batch_size <= 0:
        parser.error("batch-size must be positive")

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
    completed, cached = load_existing_results(output, records_by_id)

    pending = [record for record in records if record["id"] not in completed]
    with output.open("a", encoding="utf-8") as sink:
        for start in range(0, len(pending), args.batch_size):
            chunk = pending[start:start + args.batch_size]
            unique = {}
            for record in chunk:
                key = cache_key(record)
                if key not in cached and key not in unique:
                    unique[key] = record

            batch_results = {}
            if unique:
                request_records = list(unique.values())
                if args.batch_size == 1:
                    record = request_records[0]
                    raw, parsed = call_with_retries(
                        lambda: call_model(
                            args.base_url, args.model, record, args.max_tokens,
                            args.temperature, args.timeout,
                        ),
                        args.retry_attempts, args.retry_delay,
                    )
                    batch_results[cache_key(record)] = (raw, parsed)
                else:
                    batch_results.update(extract_batch_with_fallback(args, request_records))

            for record in chunk:
                result = {
                    "id": record["id"],
                    "source_url": record.get("source_url", ""),
                    "model": args.model,
                    "base_url": args.base_url,
                }
                key = cache_key(record)
                prior = cached.get(key)
                if prior:
                    result.update({
                        "status": "ok", "parsed": prior["parsed"],
                        "raw": prior.get("raw", ""), "reused_from": prior["id"],
                    })
                else:
                    raw, parsed = batch_results[key]
                    result.update({
                        "status": "ok" if parsed else "invalid_json",
                        "parsed": parsed, "raw": raw,
                        "request_batch_size": len(unique),
                    })
                sink.write(json.dumps(result, ensure_ascii=True) + "\n")
                sink.flush()
                completed.add(record["id"])
                if result.get("status") == "ok":
                    cached[key] = result
                print(f"processed {record['id']}", flush=True)


if __name__ == "__main__":
    main()
