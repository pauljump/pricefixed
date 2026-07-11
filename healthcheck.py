#!/usr/bin/env python3
"""
healthcheck.py — run every registered source and report which feeds are live.

Feeds break constantly: landlords rebuild sites, rotate endpoints, change payloads.
This is how the repo stays honest about it. Run it on a schedule; it refreshes the
status table in README.md and exits nonzero if any feed is down, so a cron or CI job
can turn a broken feed into an alert instead of silence.

    python3 healthcheck.py            # check all, refresh README, print a table
    python3 healthcheck.py --quiet    # just the exit code (0 = all green)

No dependencies. Python 3.9+ standard library only.
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pricefixed.adapters import ADAPTERS

START = "<!-- FEED-STATUS:START -->"
END = "<!-- FEED-STATUS:END -->"
README = Path(__file__).parent / "README.md"


def check_one(adapter_cls):
    """Run a source's pull() and classify the result. A live feed returns rows;
    zero rows or an exception both count as down (a healthy source always has units)."""
    t0 = time.monotonic()
    try:
        rows = adapter_cls().pull()
        dt = time.monotonic() - t0
        if rows:
            return {"ok": True, "count": len(rows), "secs": dt, "note": ""}
        return {"ok": False, "count": 0, "secs": dt, "note": "returned 0 listings"}
    except Exception as e:  # noqa: BLE001 — any failure is a down feed
        return {"ok": False, "count": 0, "secs": time.monotonic() - t0, "note": type(e).__name__ + ": " + str(e)[:80]}


def build_table(results):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    green = sum(1 for _, r in results if r["ok"])
    lines = [
        START,
        f"**Feed status** — {green}/{len(results)} live, checked {today}",
        "",
        "| source | status | listings | note |",
        "|---|---|---|---|",
    ]
    for name, r in sorted(results, key=lambda x: (not x[1]["ok"], x[0])):
        badge = "🟢 live" if r["ok"] else "🔴 down"
        count = str(r["count"]) if r["ok"] else "—"
        lines.append(f"| `{name}` | {badge} | {count} | {r['note']} |")
    lines.append(END)
    return "\n".join(lines)


def update_readme(table):
    if not README.exists():
        return False
    text = README.read_text()
    if START not in text or END not in text:
        return False
    head = text[: text.index(START)]
    tail = text[text.index(END) + len(END):]
    README.write_text(head + table + tail)
    return True


def main():
    quiet = "--quiet" in sys.argv
    results = []
    for name, cls in ADAPTERS.items():
        if not quiet:
            print(f"  checking {name} ...", end=" ", flush=True)
        r = check_one(cls)
        results.append((name, r))
        if not quiet:
            print(("🟢 %d" % r["count"]) if r["ok"] else ("🔴 %s" % r["note"]))

    table = build_table(results)
    wrote = update_readme(table)
    down = [n for n, r in results if not r["ok"]]

    if not quiet:
        print()
        print(table.replace(START, "").replace(END, "").strip())
        print()
        print(f"  README {'updated' if wrote else 'NOT updated (markers missing)'}")
        if down:
            print(f"  DOWN: {', '.join(down)}")
        else:
            print("  all feeds live")

    return len(down)


if __name__ == "__main__":
    sys.exit(main())
