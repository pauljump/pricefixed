# BIS certificate capture: BIN 1082857 / 12 Stuyvesant Oval

This is a targeted DOB document review for a Stuyvesant Town address. It is
source evidence only; no canonical units were imported.

- Retrieval: 2026-08-08 ET / 2026-08-09 UTC
- BIS property profile: `https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet?bin=1082857`
- C/O index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=0&allbin=1082857`
- BIS premise: `12 STUYVESANT OVAL MANHATTAN`
- BIN: `1082857`
- Block/lot: `972/1`
- BBL: `1009720001`
- Local capture directory: `/tmp/pricefixed-dob-capture/1082857/`
- OCR method: local Apple Vision helper; sidecars are in `/tmp/pricefixed-dob-capture/1082857/ocr/`

## Captured certificate set

The public index listed 49 files: the 1948 original `M000033781.PDF`,
`110148652T001.PDF` through `T018.PDF`, and `110148652-19.PDF` through
`-48.PDF`. Twenty-eight files were captured and OCR-reviewed, including the
original, the latest available temporary certificate, all `T001`–`T017`
certificates, and amendments `-19`–`-27`.

| Certificate | SHA-256 | Review result |
| :--- | :--- | :--- |
| `M000033781.PDF` | `89d88da11b76a95b91b172eceb4c25834580b419b9f5924c89401df24aad6391` | 1948 certificate for Building 17 / Units 1–3; two apartments in the service level, seven on the first story, and eight per upper floor; no apartment labels. |
| `110148652T018.PDF` | `bfe405de1c8c815821fe4e48ec961ae545521a0922a9ced580865ebac4c9eb44` | 2012 temporary certificate for 12 Stuyvesant Oval / BIN 1082857; three numbered sections and 315 dwelling units, but no apartment labels. |
| `110148652T001.PDF`–`T017.PDF`, `110148652-19.PDF`–`-27.PDF` | Individual hashes and raw PDFs are retained in the capture directory. | All OCR-reviewed records repeat section-level occupancy counts; none expose an individual apartment identity. |

## External access blocker

The remaining amendments `110148652-28.PDF` through `-48.PDF` were not
retrievable in this pass. After the 28 successful captures, the BIS/Akamai
edge returned `Access Denied` for both the C/O content endpoint and fresh C/O
index requests. This is a source-access limitation, not evidence that the
remaining documents are empty. The exact URLs and filenames remain known from
the public index for a later retry after the edge window clears.

## Finding

The 28 reviewed documents consistently use `UNIT #1`–`UNIT #3` as building
sections and describe apartment counts per story. They do not provide a
floor-by-floor apartment roster. No canonical units were added.
