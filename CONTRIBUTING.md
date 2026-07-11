# Contributing

A new source is about 30 lines. The framework handles HTTP, retries, the database,
price-history snapshots, and marking gone listings inactive — an adapter just returns
listing dicts.

## Add a source

1. Create `pricefixed/adapters/yourlandlord.py`:

```python
from ..core import SourceAdapter, fetch
import json

class YourLandlordAdapter(SourceAdapter):
    name = "yourlandlord"
    description = "Your Landlord — N buildings"

    def pull(self):
        data = json.loads(fetch("https://.../availability.json"))
        out = []
        for u in data["units"]:
            out.append({
                "source_id": u["id"],        # the only required field
                "address": u.get("address"),
                "unit_number": u.get("unit"),
                "bedrooms": u.get("beds"),
                "price": u.get("rent"),
                "zipcode": u.get("zip"),
                "raw_json": json.dumps(u),   # always keep the raw record
            })
        return out
```

2. Register it in `pricefixed/adapters/__init__.py`.
3. Test: `python3 scrape.py --source yourlandlord --db /tmp/test.db`
4. Open a PR.

See `FEEDS.md` for the full list of NYC sources waiting to be built, tiered by difficulty.

## Ground rules

- **Landlord-direct feeds only.** Public availability data landlords publish to lease their
  units — not anything behind a login or an access control.
- **Be gentle.** Honor rate limits, add a small delay between paged requests, don't hammer.
- **Standard library only** where possible. Keep the install a one-liner with zero dependencies.
- **Keep `raw_json`.** Always store the source's raw record so nothing is lost to a mapping bug.

Full-city adapters (a whole platform like RentCafe or AppFolio at once) are especially welcome —
that's how this scales past NYC.
