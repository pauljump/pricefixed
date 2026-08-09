# The NYC source map

This is the plan for compiling every apartment in the city. Each row is a source and an adapter waiting to be written. The goal is not to hand-build all of them; it is to map them all so anyone, human or AI, can crank through them. See [`COMPILE.md`](COMPILE.md) for how to turn a row into a working adapter.

For the manager-by-manager research queue, see [`docs/manager-feed-map.md`](docs/manager-feed-map.md), the generated [`data/manager_feed_registry.jsonl`](data/manager_feed_registry.jsonl), the flat [`data/public_leasing_paths.jsonl`](data/public_leasing_paths.jsonl), and its [runner documentation](docs/manager-feed-registry.md). The registry now records explicit property and leasing links exposed by official sites, while keeping confirmed public feeds separate from unverified vendor hypotheses.

**The strategy, in order of leverage:**

1. **Brokerages, for IDX/RLS-syndicated public listings.** A brokerage's own public
   search (Corcoran, Elliman, Compass) may return both its exclusives and listings
   syndicated to it through IDX/MLS, including REBNY RLS records in NYC. Named source
   adapters preserve provenance while collecting current public availability. See
   the [Brokerages](#brokerages-and-idxrls-syndication) section.
2. **Platforms.** Most landlords do not run a custom site. They rent software. Support
   a platform once and every participating landlord can be represented through the
   same adapter pattern. This is why the source count and the coverage are not the
   same number.
3. **Then the big portfolios** that run their own sites.
4. **Then the broker marketplaces** for the no-fee and small-landlord inventory.
5. **Then the walled aggregators** (StreetEasy, Zillow, and the rest). This is where most small-building units actually list, and it is the hardest tier. It is the endgame, and it is literally the walled gardens this project is named against.

**The open/private line for brokerages:** we pull only *current, on-market* asking listings — the same category as a landlord publishing its own vacancies. The *closed* sold/rented history the same backends can serve is a separate thing and is out of scope for these open adapters. Keep new brokerage adapters on the active-listings side of that line.

**Columns:**
- **Difficulty:** `easy` open JSON, no auth · `medium` HTML/DOM scrape or a token you can grab from the page · `hard` walled, needs a headless browser and patience.
- **Terms:** ✅ the source exposes per-lease-length pricing (the most valuable field, and where length-of-lease steering shows up).
- **Status:** ✅ shipped · 🔨 mechanism known, adapter not written · 🔬 needs recon.

---

## Tier 0 — Shipped (the reference implementations)

Ten live. Copy these when building new ones.

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
| Dermot Company | public Nestio API called by official building pages | easy | | current listings across 17 confirmed NY properties | ✅ |
| Spherexx / AdKast (Marquis, Kings & Queens) | official page + public paginated AJAX | medium | | current listings across 2 confirmed portals | ✅ |
| C+C Apartment Management | official public availability table | easy | | current listings on the public table | ✅ |
| Brodsky Organization | official rentals index + explicit apartment JSON-LD pages | easy | | current listings on official rentals page | ✅ |
| Manhattan Skyline Management | public `/api/units` feed + linked official unit detail pages | medium | | current listings with exact address on detail pages | ✅ |

## Tier 1 — Platforms (the multipliers)

Support one platform adapter and many landlord sites can share it. This is the
highest-leverage work left.

| Platform | Landlords on it (NYC) | Mechanism | Status |
|---|---|---|---|
| **Yardi RentCafe / SecureCafe** | Rockrose, RXR, Extell, Bozzuto/The Capitol, + many more (~10,000 units) | `securecafe.com` per-portal, or `api.rentcafe.com` per company code + token | 🔨 base shipped; enumerate more portals |
| **MRI ProspectConnect** | Durst, Ogden CAP, others | CSRF + POST search per community code | 🔨 shipped for 2; find more communities |
| **AppFolio** | dozens of small/mid operators | `{company}.appfolio.com/listings` — one shape, many subdomains | 🔨 enumerate NYC operators |
| **Entrata** | mid-size operators | `{company}.entrata.com` availability API | 🔬 |
| **Funnel / Nestio** | Dermot, Two Trees, Moinian, others | `nestiolistings.com/api/v2/` | 🔨 Dermot shipped; enumerate others |
| **Spherexx / AdKast** | Marquis, Kings & Queens, LeFrak | public `/ajax/getunitlist.asp` | 🔨 base shipped; enumerate confirmed pages |
| **RealPage / On-Site** | large operators | On-Site availability API | 🔬 |
| **Rent Manager / Buildium** | long tail of small operators | per-vendor API | 🔬 |

## Brokerages and IDX/RLS syndication

<a name="brokerages-and-idxrls-syndication"></a>Large NYC brokerages often run public listing searches backed by APIs. Those APIs can return the brokerage's own exclusives **and** current listings syndicated through IDX/MLS, which in NYC may include REBNY RLS records. These adapters collect only public current-listing records and keep the brokerage source ID so downstream users can audit provenance and reproduce collection.

**How to add one (the method, replicable):**
1. Find the brokerage's listing-search backend (open the site's network tab; it's usually a JSON API on a `*api*` subdomain — Corcoran: `backendapi.corcoranlabs.com`, Elliman: `core.api.elliman.com`).
2. POST the search asking for **active for-rent only** — never send a `sold`/`rented`/`closed` status filter. Paginate.
3. Look for `isIdx` / `isMLS` on the results. Those flags usually indicate a
   syndicated listing rather than the brokerage's own exclusive inventory.
4. Add a defensive filter that drops anything not currently active, so historical rows can never leak in. Keep the adapter strictly on the current-listings side of the line.
5. The API key, if any, is typically the brokerage's own public web-app key (sent by every browser). Treat it as public config, overridable by env; when it rotates, the healthcheck goes red and you update it.

| Brokerage | Backend | IDX/RLS | Mechanism | Status |
|---|---|---|---|---|
| **Corcoran** | `backendapi.corcoranlabs.com` | ✅ | POST `/api/search/listings`, active for-rent, paginated JSON backend | ✅ shipped (`corcoran`) |
| **Douglas Elliman** | `core.api.elliman.com` | ✅ (MLS-backed) | POST `/listing/filter`, `statuses:["Active"]` + `ResidentialLease`, borough×bedroom partitioned — clean JSON backend | ✅ shipped (`elliman`) |
| **Compass** | browser-rendered site | ✅ | no reachable JSON backend confirmed yet; browser-based discovery needed to document any GraphQL endpoint and per-session tokens. **Hard tier.** | 🔬 headless only |
| **Brown Harris Stevens** | browser-rendered site | likely | `bhsusa.com` returns 403 to a plain request. Browser-based discovery required. **Hard tier.** | 🔬 headless only |

**Diminishing returns, and where the additive coverage actually is.** Every NYC brokerage syndicates to/from the same REBNY RLS feed, so once Corcoran + Elliman are in, a third brokerage mostly re-pulls listings already captured (its own exclusives are the only genuinely-new part). The `dedupe` engine (`scrape.py --dedupe`) collapses the overlap. So after two clean-API brokerages, the higher-leverage next inventory is **platforms** (below) — mid-market landlords who are *not* on the broker feed — not a third brokerage that requires browser automation.

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
| REBNY RLS syndication | very large | feed licensing / partner access, or current public-listing collection through a brokerage source (see [Brokerages](#brokerages-and-idxrls-syndication)) | 🔨 via Corcoran |

## Tier 4 — The walled aggregators (the endgame)

Where most small-building units actually list, and the hardest tier: anti-automation
barriers, browser-only flows, and source-specific maintenance. This is the real
"every apartment" unlock. Pursue by fair, public means only.

StreetEasy · Zillow · Apartments.com · Craigslist · HotPads · Trulia

Also hard and high-value, owner-direct: A&E Real Estate · Equity Residential · Gotham · Silverstein.

---

**Beyond NYC:** the framework is city-agnostic. The platform adapters (RentCafe, AppFolio, Entrata, Funnel) run nationwide, so they port to any city with a config change. NYC first because it is the hardest and the most walled. Want your city next? Open an issue or send a PR.
