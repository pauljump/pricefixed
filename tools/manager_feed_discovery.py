#!/usr/bin/env python3
"""Build a public manager/feed discovery registry from NYBits.

The default run only reads the public NYBits manager index and manager profiles.
With --probe-websites it performs one bounded GET of each distinct official
website and records vendor fingerprints visible in that homepage. With
--discover-pages it follows a small number of explicit property, rental,
availability, and leasing links exposed by those pages. It never probes guessed
endpoints or accesses account-only areas.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


NYBITS_BASE = "https://www.nybits.com/"
DIRECTORY_URL = urljoin(NYBITS_BASE, "managers/residential_property_managers.html")

USER_AGENT = "pricefixed-manager-feed-discovery/1.0 (+public research; contact via repository)"
MAX_BODY_BYTES = 600_000
MAX_PAGE_LINKS = 12

PAGE_KEYWORDS = (
    "apartment",
    "apartments",
    "availability",
    "available",
    "building",
    "buildings",
    "community",
    "communities",
    "floorplan",
    "floor-plan",
    "floor plan",
    "homes",
    "lease",
    "leasing",
    "listings",
    "properties",
    "property",
    "rent",
    "rental",
    "rentals",
    "residential",
    "units",
    "vacancies",
    "vacancy",
)

SKIP_KEYWORDS = (
    "about",
    "blog",
    "career",
    "contact",
    "cookie",
    "privacy",
    "terms",
)

ASSET_SUFFIXES = (
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
    ".xml",
)

VENDOR_PATTERNS = {
    "securecafe": ("securecafe.com", "rentcafe.com"),
    "appfolio": ("appfolio.com",),
    "mri_prospectconnect": ("prospectconnect.com", "mrisoftware.com"),
    "entrata": ("entrata.com",),
    "funnel_nestio": ("nestiolistings.com", "funnelleasing.com"),
    "realpage": ("realpage.com", "on-site.com"),
    "buildium": ("buildium.com",),
}


class LinkParser(HTMLParser):
    """Collect anchor text and hrefs without executing page JavaScript."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_map = dict(attrs)
        self._href = attrs_map.get("href")
        self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self._href is None:
            return
        text = " ".join(" ".join(self._text).split())
        self.links.append({"href": self._href, "text": text})
        self._href = None
        self._text = []


def fetch_public(url: str, timeout: float = 30.0) -> tuple[int, str, str, str | None]:
    """Fetch one public page and return status, final URL, body, error."""
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_BODY_BYTES).decode("utf-8", errors="replace")
            return response.status, response.geturl(), body, None
    except Exception as exc:  # noqa: BLE001 - discovery records source failures
        return 0, url, "", f"{type(exc).__name__}: {exc}"


def parse_links(html: str, base_url: str) -> list[dict[str, str]]:
    parser = LinkParser()
    parser.feed(html)
    return [
        {"text": link["text"], "url": urljoin(base_url, unescape(link["href"]))}
        for link in parser.links
        if link.get("href")
    ]


def _clean_text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _stats_after_anchor(html: str, match_end: int) -> dict[str, int | None]:
    next_anchor = html.find("<a", match_end)
    chunk = html[match_end:next_anchor if next_anchor >= 0 else match_end + 1200]
    text = unescape(_clean_text(chunk))

    def number(pattern):
        found = re.search(pattern, text, re.I)
        return int(found.group(1)) if found else None

    return {
        "buildings_managed": number(r"(\d+)\s+buildings?\s+under\s+management"),
        "managed_rentals": number(r"(\d+)\s+managed\s+rentals?"),
        "brokered_rentals": number(r"(\d+)\s+brokered\s+rentals?"),
    }


def extract_manager_entries(html: str, base_url: str = NYBITS_BASE) -> list[dict]:
    """Extract manager profile links and nearby directory counts."""
    entries = []
    anchor_re = re.compile(
        r"<a\b[^>]*href\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", re.I | re.S
    )
    for match in anchor_re.finditer(html):
        href = unescape(match.group(2))
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != urlparse(base_url).netloc:
            continue
        if not re.match(r"^/managers/[^/]+\.html$", parsed.path):
            continue
        if "_letter_managers.html" in parsed.path or parsed.path.endswith("residential_property_managers.html"):
            continue
        name = " ".join(unescape(re.sub(r"<[^>]+>", " ", match.group(3))).split())
        if not name:
            continue
        slug = Path(parsed.path).stem
        entry = {"manager_slug": slug, "manager_name": name, "profile_url": url}
        entry.update(_stats_after_anchor(html, match.end()))
        entries.append(entry)

    unique = {}
    for entry in entries:
        unique.setdefault(entry["profile_url"], entry)
    return sorted(unique.values(), key=lambda row: (row["manager_name"].lower(), row["profile_url"]))


def _domain_from_text(text: str) -> str | None:
    candidate = text.strip().strip(".,;()")
    if not re.match(r"^(?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/.*)?$", candidate, re.I):
        return None
    if not candidate.startswith(("http://", "https://")):
        candidate = "https://" + candidate
    parsed = urlparse(candidate)
    if not parsed.hostname or parsed.hostname.endswith("nybits.com"):
        return None
    return candidate.rstrip("/")


def extract_official_website(html: str, profile_url: str) -> tuple[str | None, list[str]]:
    links = parse_links(html, profile_url)
    candidates = []
    for link in links:
        domain_from_text = _domain_from_text(link["text"])
        if domain_from_text:
            candidates.append(domain_from_text)
        parsed = urlparse(link["url"])
        if parsed.hostname and not parsed.hostname.endswith("nybits.com"):
            if parsed.scheme in ("http", "https") and not re.search(r"hud\.gov|nyc\.gov|facebook|twitter|linkedin", parsed.hostname, re.I):
                candidates.append(link["url"].rstrip("/"))
    deduped = list(dict.fromkeys(candidates))
    return (deduped[0] if deduped else None), deduped


def classify_vendor(values: list[str]) -> list[str]:
    joined = " ".join(values).lower()
    return [vendor for vendor, patterns in VENDOR_PATTERNS.items() if any(pattern in joined for pattern in patterns)]


def _same_site(hostname: str | None, official_host: str | None) -> bool:
    if not hostname or not official_host:
        return False
    hostname = hostname.lower().removeprefix("www.")
    official_host = official_host.lower().removeprefix("www.")
    return hostname == official_host or hostname.endswith("." + official_host)


def _page_kind(text: str, url: str, vendor_hints: list[str]) -> str:
    if vendor_hints:
        return "vendor_portal"
    value = f"{text} {url}".lower()
    if any(word in value for word in ("availability", "available", "vacanc", "units")):
        return "availability"
    if any(word in value for word in ("lease", "leasing", "rent", "rental")):
        return "leasing"
    return "property"


def select_public_links(
    links: list[dict[str, str]], official_url: str, source_url: str
) -> list[dict[str, str | list[str]]]:
    """Keep explicit public property/leasing links from one already-fetched page."""
    official_host = urlparse(official_url).hostname
    selected = []
    seen = set()
    for link in links:
        url = link.get("url", "").split("#", 1)[0].rstrip("/")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            continue
        if parsed.path.lower().endswith(ASSET_SUFFIXES):
            continue
        vendor_hints = classify_vendor([url, link.get("text", "")])
        same_site = _same_site(parsed.hostname, official_host)
        value = f"{link.get('text', '')} {parsed.path} {parsed.query}".lower()
        has_page_keyword = any(keyword in value for keyword in PAGE_KEYWORDS)
        has_skip_keyword = any(keyword in value for keyword in SKIP_KEYWORDS)
        if not vendor_hints and not same_site:
            continue
        if has_skip_keyword and not vendor_hints:
            continue
        if not has_page_keyword and not vendor_hints:
            continue
        if url in seen:
            continue
        seen.add(url)
        selected.append(
            {
                "url": url,
                "source_url": source_url,
                "anchor_text": " ".join(link.get("text", "").split()),
                "page_kind": _page_kind(link.get("text", ""), url, vendor_hints),
                "vendor_hints": vendor_hints,
            }
        )
    kind_order = {"vendor_portal": 0, "availability": 1, "leasing": 2, "property": 3}
    selected.sort(key=lambda item: (kind_order.get(item["page_kind"], 9), item["url"]))
    return selected[:MAX_PAGE_LINKS]


def discover_public_pages(url: str, max_pages: int = 8) -> list[dict]:
    """Follow at most two hops of explicit public property/leasing links."""
    _, homepage_final, homepage_html, homepage_error = fetch_public(url, timeout=10.0)
    if homepage_error:
        return []

    official_url = homepage_final
    queue = select_public_links(parse_links(homepage_html, homepage_final), official_url, homepage_final)
    results = []
    seen = {homepage_final.rstrip("/")}
    while queue and len(results) < max_pages:
        candidate = queue.pop(0)
        candidate_url = str(candidate["url"])
        if candidate_url in seen:
            continue
        seen.add(candidate_url)
        status, final_url, html, error = fetch_public(candidate_url, timeout=10.0)
        vendor_hints = classify_vendor([candidate_url, final_url, html[:MAX_BODY_BYTES]])
        result = {
            **candidate,
            "http_status": status or None,
            "final_url": final_url,
            "vendor_hints": sorted(set(candidate["vendor_hints"] + vendor_hints)),
            "content_sha256": hashlib.sha256(html.encode()).hexdigest() if html else None,
            "error": error,
        }
        results.append(result)
        if error:
            continue
        if candidate["page_kind"] == "vendor_portal":
            continue
        next_links = select_public_links(parse_links(html, final_url), official_url, final_url)
        for next_link in next_links:
            if next_link["url"] not in seen:
                queue.append(next_link)
    return results


def probe_website(url: str) -> dict:
    # A dead manager link should not hold up the whole census for 30 seconds.
    status, final_url, html, error = fetch_public(url, timeout=10.0)
    if error:
        return {"website_status": "fetch_error", "website_http_status": None, "website_error": error}
    links = parse_links(html, final_url)
    markers = [link["url"] for link in links if urlparse(link["url"]).hostname]
    vendor_hints = classify_vendor([final_url, *markers, html[:MAX_BODY_BYTES]])
    return {
        "website_status": "public_page_seen",
        "website_http_status": status,
        "website_final_url": final_url,
        "website_vendor_hints": vendor_hints,
        "website_content_sha256": hashlib.sha256(html.encode()).hexdigest(),
    }


def discover(args) -> list[dict]:
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    # The canonical directory currently contains the manager links and counts.
    # Letter pages remain useful for manual research but are not needed for the
    # initial census, so the default run does one index request only.
    index_pages = [DIRECTORY_URL]
    entries = []
    for index_url in index_pages:
        _, final_url, html, error = fetch_public(index_url)
        if error:
            print(f"index error: {index_url}: {error}", file=sys.stderr)
            continue
        entries.extend(extract_manager_entries(html, final_url))
        time.sleep(args.delay)

    unique = {}
    for entry in entries:
        unique.setdefault(entry["profile_url"], entry)
    selected = sorted(unique.values(), key=lambda row: (row["manager_name"].lower(), row["profile_url"]))
    if args.limit:
        selected = selected[:args.limit]

    rows = []
    website_cache = {}
    for number, entry in enumerate(selected, start=1):
        status, final_url, html, error = fetch_public(entry["profile_url"])
        website_url = website_host = None
        website_candidates = []
        profile_vendors = []
        if not error:
            website_url, website_candidates = extract_official_website(html, final_url)
            profile_vendors = classify_vendor([final_url, html[:MAX_BODY_BYTES]])

        row = {
            **entry,
            "checked_at": checked_at,
            "directory_url": DIRECTORY_URL,
            "profile_http_status": status or None,
            "profile_error": error,
            "official_website_url": website_url,
            "official_website_candidates": website_candidates,
            "official_website_host": urlparse(website_url).hostname if website_url else None,
            "vendor_hints_from_profile": profile_vendors,
            "vendor_hints_from_website": [],
            "feed_status": "unknown",
            "transport_confidence": "unknown",
            "evidence_urls": [entry["profile_url"], DIRECTORY_URL],
        }
        if args.probe_websites and website_url:
            cache_key = website_url.lower()
            if cache_key not in website_cache:
                website_cache[cache_key] = probe_website(website_url)
                time.sleep(args.delay)
            row.update(website_cache[cache_key])
            row["vendor_hints_from_website"] = row.get("website_vendor_hints", [])
            if row.get("website_final_url") and row["website_final_url"] not in row["evidence_urls"]:
                row["evidence_urls"].append(row["website_final_url"])
        if args.discover_pages and website_url:
            row["public_page_candidates"] = discover_public_pages(
                website_url, max_pages=args.max_pages
            )
            for page in row["public_page_candidates"]:
                evidence_url = page.get("final_url") or page.get("url")
                if evidence_url and evidence_url not in row["evidence_urls"]:
                    row["evidence_urls"].append(evidence_url)
        rows.append(row)
        print(f"[{number}/{len(selected)}] {entry['manager_name']}", file=sys.stderr)
        time.sleep(args.delay)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="JSONL registry path")
    parser.add_argument("--limit", type=int, help="Only keep the first N managers after sorting")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between public requests (default: 1)")
    parser.add_argument("--probe-websites", action="store_true", help="Fetch each distinct official homepage once")
    parser.add_argument(
        "--discover-pages",
        action="store_true",
        help="Follow explicit public property/leasing links from official sites",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=8,
        help="Maximum linked pages to check per manager (default: 8)",
    )
    args = parser.parse_args(argv)
    if args.delay < 0.2:
        parser.error("--delay must be at least 0.2 seconds")
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")

    rows = discover(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")
    print(f"wrote {len(rows)} manager rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
