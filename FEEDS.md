# The NYC source map

This is the plan for compiling every apartment in the city. Each row is a source and an adapter waiting to be written. The goal is not to hand-build all of them; it is to map them all so anyone, human or AI, can crank through them. See [`COMPILE.md`](COMPILE.md) for how to turn a row into a working adapter.

**The strategy, in order of leverage:**

1. **Platforms first.** Most landlords do not run a custom site. They rent software. Crack the *platform* once and every landlord on it comes with it. This is why the source count and the coverage are not the same number.
2. **Then the big portfolios** that run their own sites.
3. **Then the broker marketplaces** for the no-fee and small-landlord inventory.
4. **Then the walled aggregators** (StreetEasy, Zillow, and the rest). This is where most small-building units actually list, and it is the hardest tier. It is the endgame, and it is literally the walled gardens this project is named against.

**Columns:**
- **Difficulty:** `easy` open JSON, no auth · `medium` HTML/DOM scrape or a token you can grab from the page · `hard` walled, needs a headless browser and patience.
- **Terms:** ✅ the source exposes per-lease-length pricing (the most valuable field, and where length-of-lease steering shows up).
- **Status:** ✅ shipped · 🔨 mechanism known, adapter not written · 🔬 needs recon.

---

## Tier 0 — Shipped (the reference implementations)

Nine live. Copy these when building new ones.

| Source | Mechanism | Difficulty | Terms | Est. units | Status |
|---|---|---|---|---|---|
| StuyTown / Beam Living | JSON API (`units.stuytown.com`) | easy | ✅ | ~330 | ✅ |
| TF Cornerstone | one static JSON feed | easy | | ~9,000 | ✅ |
| Nooklyn (broker marketplace) | JSON API | easy | | ~1,500 | ✅ |
| AvalonBay | `apis.avalonbay.com/search/units` | easy | | ~5,000 | ✅ |
| SecureCafe (Yardi/RentCafe portals) | per-portal HTML | medium | | ~250+ | ✅ |
| Stonehenge | Salesforce apexrest | easy | | ~80 | ✅ |
| Ogden CAP | MRI ProspectConnect | medium | | ~50 | ✅ |
| Durst | MRI ProspectConnect | medium | ✅ | ~30 live | ✅ |
| Glenwood | two-hop HTML scrape | medium | | ~30 | ✅ |

## Tier 1 — Platforms (the multipliers)

Crack one, get everyone on it. This is the highest-leverage work left.

| Platform | Landlords on it (NYC) | Mechanism | Status |
|---|---|---|---|
| **Yardi RentCafe / SecureCafe** | Rockrose, Brodsky, RXR, Extell, + many more (~10,000 units) | `securecafe.com` per-portal, or `api.rentcafe.com` per company code + token | 🔨 base shipped; enumerate more portals |
| **MRI ProspectConnect** | Durst, Ogden CAP, others | CSRF + POST search per community code | 🔨 shipped for 2; find more communities |
| **AppFolio** | dozens of small/mid operators | `{company}.appfolio.com/listings` — one shape, many subdomains | 🔨 enumerate NYC operators |
| **Entrata** | mid-size operators | `{company}.entrata.com` availability API | 🔬 |
| **Funnel / Nestio** | Two Trees, Moinian, others | `nestiolistings.com/api/v2/` | 🔬 |
| **RealPage / On-Site** | large operators | On-Site availability API | 🔬 |
| **Rent Manager / Buildium** | long tail of small operators | per-vendor API | 🔬 |

## Tier 2 — Big portfolios (own sites)

| Source | Est. units | Mechanism | Status |
|---|---|---|---|
| Related Rentals | ~5,000 | Drupal/React hybrid, paginated DOM | 🔬 (rebuilt recently; will rot) |
| LeFrak | ~4,600 | Spherexx server-rendered HTML | 🔨 |
| Rudin | ~2,400 | server-rendered building pages | 🔨 |
| UDR | ~2,600 | counts server-side; unit detail needs headless | 🔬 |
| Rose Associates | ~3,000 | own portal | 🔬 |
| Bozzuto | ~2,000 | Algolia index | 🔨 |
| Two Trees | ~2,000 | Nestio (see platform) | 🔬 |
| Rockrose / RXR / Extell | via RentCafe | (see platform) | 🔨 |
| Pan Am Equities | ~1,000 | WordPress DOM | 🔬 |

## Tier 3 — Broker marketplaces (the small-landlord tail)

| Source | Est. units | Mechanism | Status |
|---|---|---|---|
| Nooklyn | ~1,500 | JSON API | ✅ |
| RentHop | large | anti-bot; API behind the site | hard |
| Localize.city | large | JSON API | 🔬 |
| RealtyHop | medium | JSON API | 🔬 |
| REBNY RLS syndication | very large | feed licensing / partner access | 🔬 |

## Tier 4 — The walled aggregators (the endgame)

Where most small-building units actually list, and the hardest tier: aggressive bot walls, headless browsers, and a permanent cat-and-mouse. This is the real "every apartment" unlock. Pursue by fair, public means only.

StreetEasy · Zillow · Apartments.com · Craigslist · HotPads · Trulia

Also hard and high-value, owner-direct: A&E Real Estate · Equity Residential · Gotham · Silverstein.

---

**Beyond NYC:** the framework is city-agnostic. The platform adapters (RentCafe, AppFolio, Entrata, Funnel) run nationwide, so they port to any city with a config change. NYC first because it is the hardest and the most walled. Want your city next? Open an issue or send a PR.
