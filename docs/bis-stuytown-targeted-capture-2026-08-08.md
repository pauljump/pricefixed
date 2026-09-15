# Targeted BIS capture for unresolved Stuyvesant Town addresses

This is a duplicate-controlled, browser-assisted review of the next ranked
Stuyvesant Town BIN targets. It was run on 2026-08-08 after the existing BIS,
HPD, ACRIS, and DOB description passes. The purpose was to find a document
that names an apartment at an exact catalog address. Counts, floor-level
occupancy, and building/occupancy-section identifiers remain non-canonical.

## Results

| BIN | Queue target(s) | BIS index premise | Review | Catalog result |
| :--- | :--- | :--- | :--- | :--- |
| `1082871` | `282`, `288`, `298 1 AVE` | `284 1 AVENUE` | 26 visible C/O files downloaded/checked. The current and amended certificates identify `300 1ST AVENUE`; they report six or 88 dwelling units and floor-level apartment counts, but no apartment labels. | No units. The certificate-face premise does not exactly match any of the three queue targets. |
| `1082859` | `516`, `518 E 20 ST` | `510 EAST 20 STREET` | 12 distinct visible C/O references checked. The historical scans include other premises and shared-lot occupancy records; no exact target apartment label was found. | No units. |
| `1082872` | `262`, `264 1 AVE` | `254 FIRST AVENUE` | The BIS index says there are no Certificates of Occupancy on file. | No units. |
| `1082726` | `251 AVE C` | `245 AVENUE C` | Five visible scans checked. The historical certificates list several premises together, including `245 Avenue C`, and use `Building #35 Unit #1/#2/#3` style section identifiers with seven/eight apartments per floor. They do not name individual apartments or establish an exact-address crosswalk to `251 AVE C`. | Rejected as shared-BBL/building-section evidence; no units. |
| `1082771`, `1082848`, `1082862`, `1082864`, `1082875`, `1082886` | Other single-address ranked targets | Different BIS premises than the queue rows, or no certificates (`1082864`) | Index-only identity check completed. The visible certificate sets are available for later targeted review, but the index premises are not exact matches to the unresolved queue rows. | No units imported. |

The `Unit #` strings in the `1082726` scans are not apartment labels. They are
building/occupancy-section identifiers, exactly like the previously reviewed
HPD I-card and BIS records. A certificate that lists several premises under a
shared BBL cannot be used to assign that identifier to one address.

## Representative source evidence

The BIS index pages and the browser-visible PDF form references are the source
URLs. The browser download cache retains the raw PDF bytes under
`/Users/mini-home/Downloads/CofoDocumentContentServlet (N).pdf`; the following
representative files were retained and hashed during review:

| Source | Browser-visible PDF reference | SHA-256 | Finding |
| :--- | :--- | :--- | :--- |
| [BIN 1082871 C/O index](https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=0&allbin=1082871) | `121186304T001.PDF` | `460afb1c3b38543471f1fc3158875c1ea56b92a3dffef1a5937388b6906b97e0` | `300 1ST AVENUE`; six dwelling units; floor-level count only. |
| [BIN 1082726 C/O index](https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=0&allbin=1082726) | `M000033167.PDF` | `4c67fd48532780049384dec3b3b6812298a7d987b01fe9346957c75ee22dbb0f` | Shared-premise scan with `Building #35 Unit #3`; seven/eight apartments per floor; no apartment labels. |

The full visible certificate queues were not converted into catalog records.
The raw candidates remain reviewable, while the exact-address queue remains
at 228 unresolved Stuyvesant Town/Peter Cooper Village addresses.

## Next blocker

This pass exhausts the practical BIS C/O index lane for the highest-yield
Stuyvesant Town BINs reviewed so far. BIS is useful for identity checks and
capacity observations, but it is not exposing an apartment roster for these
shared-lot records. The next productive source must be an address-specific
unit-bearing DOB NOW filing, filed plan, schedule, or an official manager
availability feed. Until one of those sources supplies an explicit label tied
to the exact premise, the named-unit layer must not grow from these documents.
