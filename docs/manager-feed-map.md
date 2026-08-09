# Manager Feed Map

This is the working map of where NYC rental managers publish availability.
It is not a claim that NYBits has a master feed. NYBits says managers can
provide a website, a weekly spreadsheet, or an XML feed, and that NYBits can
also accept listings posted by hand. The public manager directory is therefore
useful for finding who manages a building, but it is not the source of truth
for every apartment.

For the separate investigation of NYBits's public code fingerprints, feed
instructions, and public GitHub evidence, see [`nybits-deep-dive.md`](nybits-deep-dive.md).

Sources:

- [NYBits manager directory](https://www.nybits.com/managers/residential_property_managers.html)
- [NYBits feed instructions](https://www.nybits.com/add.html)

## How To Read This

- **Confirmed feed** means Pricefixed has a public endpoint or page shape that
  an adapter can collect without an account.
- **Public portal** means the manager exposes current availability, but we have
  not yet confirmed a stable machine-readable endpoint.
- **Candidate** means the public site identifies a likely vendor or path, but
  it still needs a bounded test before we add it to a collector.
- A manager may use more than one path across its portfolio. Record the
  property, vendor, URL, and date separately instead of assuming one feed covers
  every building.

## Confirmed Feeds

| Manager or portfolio | Public source | What it gives us | Pricefixed status |
|---|---|---|---|
| Beam Living / StuyTown | [`units.stuytown.com/api/units`](https://units.stuytown.com/api/units?itemsOnPage=500&Order=low-price) | JSON availability with unit-level asking rents and lease terms | Shipped in `stuytown` |
| TF Cornerstone | [`cdn.tfc.com/tfc-com/initial-data.json`](https://cdn.tfc.com/tfc-com/initial-data.json) | Portfolio JSON with properties and available units | Shipped in `tfcornerstone` |
| AvalonBay | `apis.avalonbay.com/search/units` | Public unit search response | Shipped in `avalonbay` |
| RentCafe / SecureCafe properties already found | Per-property `securecafe.com/onlineleasing/.../availableunits.aspx` pages | Public HTML tables with unit, square feet, rent, and availability | Shipped in `securecafe`; more portals still need enumeration |
| AppFolio operators already found | Public `{company}.appfolio.com/listings` pages | Public listing/map data embedded in the page | Shipped in `appfolio`; more NYC companies still need enumeration |
| Durst and Ogden CAP | MRI ProspectConnect community pages | Public community availability after the site search flow | Shipped in `durst` and `ogdencap` |
| Dermot Company | [`dermotcompany.com/state/new-york`](https://www.dermotcompany.com/state/new-york) → public `nestiolistings.com/api/v2/listings/all` calls | Current listings with exact unit labels, exact street address, price, and availability date for 17 confirmed NY communities | Shipped in `dermot`; this is not a complete roster |
| Bozzuto — The Capitol | [Official property page](https://www.bozzuto.com/apartments-for-rent/ny/new-york/the-capitol) → [`thecapitolchelsea.securecafe.com`](https://thecapitolchelsea.securecafe.com/onlineleasing/the-capitol/availableunits.aspx) | Current SecureCafe rows with exact unit labels, rent, square feet, and availability date | Shipped as `securecafe`; one confirmed Bozzuto property, not the whole portfolio |
| Marquis Apartments and Kings & Queens Apartments | Official availability pages → public `/ajax/getunitlist.asp` responses | Current rows with exact street addresses, apartment labels, prices, and availability | Shipped in `spherexx`; 2 confirmed portals, not a complete roster |
| C+C Apartment Management | [`ccmanagers.com/availability`](https://ccmanagers.com/availability/) | Public table with exact street address, apartment label, rent, and availability date | Shipped in `ccmanagers`; current table is not a complete roster |
| Brodsky Organization | [`brodsky.com/rentals`](https://www.brodsky.com/rentals) → explicit apartment detail pages with JSON-LD | Current listings with exact street address, apartment label, price, and availability | Shipped in `brodsky`; current index had 6 listings, not a complete roster |
| Manhattan Skyline Management | [`manhattanskyline.com/api/units`](https://manhattanskyline.com/api/units) → official unit detail pages | Current unit API rows joined to exact street addresses from each official detail page; rows without exact addresses are rejected | Shipped in `manhattanskyline`; 27 accepted from the current 28-row API response |
| Olnick Rentals | [`olnickrentals.com`](https://olnickrentals.com/) → explicit project availability pages | Current rows with exact street address, apartment label, bedroom/bath, square feet, and asking rent | Shipped in `olnick`; current public pages had 11 accepted listings across five project pages, not a complete roster |

## Manager-Specific Paths To Test

| Manager | Official public entry point | Observed path | Status |
|---|---|---|---|
| Rockrose | [Rockrose residential properties](https://rockrose.com/residential/) | Eleven official property pages were checked for their linked SecureCafe availability paths. Six returned “No apartments were found matching your search request” (100 Jane Street, 200 Water Street, Eagle Lofts, Hayden, Midwest Court, and The Archive); five returned HTTP 403 during the direct availability check (110 Horatio Street, 47-05 Center Boulevard, Linc LIC, Lyra, and The Cove). | Public handoffs documented; no new current unit rows to ingest; 403 paths remain browser/session candidates |
| Brodsky Organization | [Brodsky rentals](https://www.brodsky.com/rentals) → explicit apartment detail JSON-LD pages | The official index exposes current apartment URLs; detail pages carry exact unit/address, price, and availability fields. | Confirmed public feed in `brodsky`; current vacancies only |
| Bozzuto | [Bozzuto NYC rentals](https://www.bozzuto.com/apartments-for-rent/ny/new-york) | The Capitol is confirmed through the official property page and its linked public SecureCafe availability page; other Bozzuto communities remain untested. | Confirmed for The Capitol; enumerate other properties |
| RXR and Extell | Official property sites and their individual leasing pages | Likely mixed property-by-property vendor paths. Do not treat the RentCafe hypothesis as confirmed until an official property page links to a specific public portal. | Candidate: map one property per manager |
| Two Trees and Moinian | Official property sites | Likely Funnel/Nestio-style or property-specific listing pages. No universal public endpoint has been confirmed. | Candidate: identify one live property path first |
| Rose Associates | [NYBits manager profile](https://www.nybits.com/managers/rose.html) and Rose property sites | Many buildings, but no portfolio-wide public feed has been confirmed. | Candidate: sample the largest live property pages |
| Greystar | Greystar property search | Official NYC search reaches individual community pages. A tested community page exposes floorplans and a building unit count, but no apartment labels in the public response. | Candidate: unit-bearing endpoint still missing; do not ingest floorplans/counts |

## Who We Can Name Today

These are the managers and operators for which we have a public feed or a
public feed-shaped leasing system. This is stronger than a guess about a
manager's software, but it still does **not** prove that the same source is the
file NYBits receives.

| Manager or operator | Evidence we can reproduce | Confidence |
|---|---|---|
| Beam Living | The StuyTown availability site exposes a unit JSON endpoint, and the `stuytown` adapter collects it. | Confirmed public feed |
| TF Cornerstone | TFC exposes a portfolio-wide JSON file, and the `tfcornerstone` adapter collects it. | Confirmed public feed |
| Durst Management | Durst availability is exposed through MRI ProspectConnect, collected by the `durst` adapter. | Confirmed public portal |
| Ogden CAP Properties | Ogden CAP availability is exposed through MRI ProspectConnect, collected by the `ogdencap` adapter. | Confirmed public portal |
| 9300 Realty | The existing SecureCafe configuration includes a 9300 Realty portfolio portal. | Confirmed vendor portal |
| Rockrose Development | Rockrose's official property pages link applicants to property-specific SecureCafe portals. The checked availability paths currently return no ingestible unit rows or access-denied responses. | Confirmed vendor handoff; public unit feed blocked |
| ABJ Properties, Patoma, A&N Management, Downtown | Each has a public AppFolio listings page with embedded unit/map data, collected by the `appfolio` adapter. | Confirmed public feed-shaped pages |
| Dermot Company | Official building pages expose community IDs and call the public Nestio availability endpoint; 17 New York properties are configured. | Confirmed public feed |
| Bozzuto Management | The Capitol's official page links to a public SecureCafe availability page with current exact unit labels. | Confirmed public feed for The Capitol; portfolio incomplete |
| Brodsky Organization | Brodsky's public rentals page exposes current building/unit listings. | Confirmed public listings; feed endpoint unknown |
| Manhattan Skyline Management | The public unit API exposes unit labels and current asking terms; official detail pages supply exact street addresses. | Confirmed public feed with address validation; current vacancies only |
| Rose Associates, Greystar, Two Trees | NYBits identifies these managers and their building portfolios, but we have not yet confirmed a stable public feed endpoint for them. | Manager confirmed; feed unknown |

The missing column is **NYBits transport**. NYBits does not publish that
column. The only reliable way to fill it is to observe the same manager's
source over time, or obtain confirmation from NYBits or the manager. We should
not turn a public availability page into a claim that the manager sends NYBits
an XML feed.

## What We Should Do Next

1. Use the [NYBits manager directory](https://www.nybits.com/managers/residential_property_managers.html)
   to create a manager-to-building queue. The directory tells us who to
   investigate, not how many units actually exist.
2. For each manager, start with one live building and record the exact public
   URL, vendor, fields, and fetch date.
3. If several buildings share the same vendor and URL shape, promote that shape
   into an adapter and keep the buildings as configuration rows.
4. Keep page-only sources in the map until a stable endpoint is verified. Do not
   invent a feed URL or label a manager as covered because one property works.
5. Run the same listings through the existing dedupe and provenance layers so a
   broker copy and a manager-direct copy remain separately auditable.

## The Important Limitation

A public manager page usually shows **current vacancies**, not every apartment
in the building. A manager feed can therefore add source-backed unit
observations and asking rents, but it cannot prove that an unlisted apartment
does not exist. The base catalog still has to come from public records and
building-level sources.
