# NYC source registry

The map of what to build. Landlord-direct sites have no bot walls — they *want* to lease —
which is the opposite of the aggregators (StreetEasy / RentHop / Citysnap all block volume).
This registry is the roadmap; each row is an adapter waiting to be written.

**Difficulty:** `easy` = open JSON, no auth · `medium` = HTML/DOM scrape or obtainable token · `hard` = walled (needs a headless browser).
**Status:** ✅ shipped in this repo · 🔨 verified endpoint, not yet written · 🔬 needs recon.

## Shipped

| Source | Type | Difficulty | Est. units |
|---|---|---|---|
| StuyTown / Beam Living | JSON API | easy | ~330 live |
| TF Cornerstone | static JSON | easy | ~9,000 total |
| Nooklyn (broker marketplace) | JSON API | easy | ~1,500 live |

## Next up — easy JSON, verified

| Source | Mechanism | Est. units | Status |
|---|---|---|---|
| AvalonBay | `apis.avalonbay.com/search/units` (client key in page) | ~5,000 | 🔨 |
| Ogden CAP | MRI ProspectConnect, POST `/Search/Search?Community=[code]` | ~2,000 | 🔨 |
| Durst | MRI ProspectConnect | ~80 live | 🔨 |
| Glenwood | WordPress JSON | ~30 live | 🔨 |
| Stonehenge | Salesforce apexrest | ~80 live | 🔨 |

## Platform plays — crack one, get many

The NYC market splits across a few property-management platforms. An adapter for the
*platform* unlocks every landlord on it.

| Platform | Landlords on it | Mechanism |
|---|---|---|
| **Yardi RentCafe** | Rockrose, Brodsky, RXR, Extell, + more (~10,000 units) | `api.rentcafe.com/rentcafeapi.aspx` — per-company code + token |
| **MRI ProspectConnect** | Durst, Ogden CAP, others | POST search per community code |
| **Funnel / Nestio** | Two Trees, Moinian, others | `nestiolistings.com/api/v2/` |

## Medium — HTML/DOM scrape

| Source | Est. units | Notes |
|---|---|---|
| Related Rentals | ~5,000 | rebuilt to a Drupal/React hybrid — paginated results, DOM parse |
| LeFrak | ~4,600 | Spherexx server-rendered HTML |
| Rudin | ~2,400 | server-rendered building pages |
| UDR | ~2,600 | counts server-side; unit detail needs a headless browser |
| Pan Am Equities | ~1,000 | WordPress DOM |
| AppFolio operators | ~50–100 each | `{company}.appfolio.com/listings` — many small operators |

## Hard — walled (need a headless browser + patience)

A&E Real Estate · Rose Associates · Equity Residential · Gotham · Silverstein. Biggest untapped inventory, aggressive bot walls. Later.

---

**Beyond NYC:** the framework is city-agnostic. Same platforms (RentCafe, AppFolio, Funnel) run
nationwide, so the platform adapters port directly. NYC first because it's the hardest and the
most walled. If you want your city next, open an issue or send a PR.
