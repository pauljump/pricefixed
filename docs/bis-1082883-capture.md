# BIS certificate capture: BIN 1082883 / 505 East 14 Street

This is a targeted DOB document review for a Stuyvesant Town address. It is
source evidence only; no canonical units were imported.

- Retrieval: 2026-08-08 ET / 2026-08-09 UTC
- BIS property profile: `https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet?bin=1082883`
- C/O index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=0&allbin=1082883`
- BIS premise: `505 EAST 14 STREET MANHATTAN`
- BIN: `1082883`
- Block/lot: `972/1`
- BBL: `1009720001`
- Local capture directory: `/tmp/pricefixed-dob-capture/1082883/`
- OCR method: local Apple Vision helper; sidecars are in `/tmp/pricefixed-dob-capture/1082883/ocr/`

## Captured certificates

| Certificate | SHA-256 | Review result |
| :--- | :--- | :--- |
| `M000033968.PDF` | `4bd04e5e9bbfddfc0009173e225ab337abcbf1f40d3269ca677ba489cefca6d9` | Describes Building #22 / numbered sections and per-floor apartment counts, but does not expose an exact street address or individual apartment labels. |
| `M000037004.PDF` | `5bbb81c87324c914c9d52a8d30c40241ab27a9a318d74251b8cf60cda5e5d7de` | Names 505–515 East 14th Street, block 972 lot 1, and numbered building sections with five/eight/six apartments per floor; no individual apartment labels. |
| `M000073157.PDF` | `9daec38216f84fd1950ce3cf4bae12f2ffdaed15326ce82d5f10d8834e02cb7a` | 1973 amendment for 505–515 East 14th Street / lot part of 1; describes Unit #1 and Unit #2 sections and per-floor counts, not apartment identities. |

## Finding

The certificate `UNIT` values are building/occupancy-section identifiers. They
are accompanied by statements such as six or eight apartments on each floor;
the documents do not provide apartment labels such as `5A` or `12-4`, nor a
floor-by-floor roster. These observations remain capacity/history evidence only.
No canonical units were added.
