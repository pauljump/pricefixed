#!/usr/bin/env python3
"""
new_adapter.py — scaffold a new source adapter.

    python3 new_adapter.py glenwood
    python3 new_adapter.py glenwood "Glenwood Management — luxury rentals"

Writes pricefixed/adapters/<name>.py prefilled from the template, then tells you
the one line to add to the registry. Fill in pull() and you have a source.
See COMPILE.md for the full loop. No dependencies; stdlib only.
"""
import re
import sys
from pathlib import Path

TEMPLATE = '''\
"""{desc}
TODO: one or two lines on the source — the feed URL and how it is shaped."""
import json

from ..core import SourceAdapter, fetch


class {cls}(SourceAdapter):
    name = "{name}"
    description = "{desc}"

    # The landlord-direct feed. Find it in the site's network tab (see COMPILE.md).
    API_URL = "https://TODO"

    def pull(self):
        data = json.loads(fetch(self.API_URL))
        out = []
        for u in data.get("TODO_units_key", []):
            out.append({{
                "source_id": str(u.get("id")),        # the only required field
                "address": u.get("address"),
                "unit_number": u.get("unit"),
                "bedrooms": u.get("beds"),
                "bathrooms": u.get("baths"),
                "price": u.get("price"),
                # If the source exposes per-lease-term pricing, keep it — it is the
                # most valuable field. lease_terms = json.dumps([{{"term": ..., "price": ...}}])
                "raw_json": json.dumps(u, default=str),   # always keep the raw record
            }})
        return out
'''


def main():
    if len(sys.argv) < 2:
        print("usage: python3 new_adapter.py <name> [description]")
        return 1
    name = sys.argv[1].strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        print(f"bad name {name!r}: use lowercase letters, digits, underscores; start with a letter")
        return 1
    desc = sys.argv[2] if len(sys.argv) > 2 else f"{name} — TODO describe the source"
    cls = "".join(p.capitalize() for p in name.split("_")) + "Adapter"

    path = Path(__file__).parent / "pricefixed" / "adapters" / f"{name}.py"
    if path.exists():
        print(f"{path} already exists — not overwriting")
        return 1
    path.write_text(TEMPLATE.format(cls=cls, name=name, desc=desc))

    print(f"created {path}")
    print("\nnext:")
    print("  1. fill in API_URL and pull() (see COMPILE.md and any file in pricefixed/adapters/)")
    print(f"  2. register it in pricefixed/adapters/__init__.py:")
    print(f"       from .{name} import {cls}")
    print(f"       ...and add {cls} to the ADAPTERS tuple")
    print(f"  3. test: python3 scrape.py --source {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
