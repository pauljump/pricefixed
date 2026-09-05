# BIS certificate capture: BIN 1082869 / 272 First Avenue

This is a targeted DOB document review for a Stuyvesant Town address. It is
source evidence only; no canonical units were imported.

- Retrieval: 2026-08-08 ET / 2026-08-09 UTC
- BIS property profile: `https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet?bin=1082869`
- C/O index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=0&allbin=1082869`
- BIS premise: `272 FIRST AVENUE MANHATTAN`
- BIN: `1082869`
- Block/lot: `972/1`
- BBL: `1009720001`
- Local capture directory: `/tmp/pricefixed-dob-capture/1082869/`
- OCR method: local Apple Vision helper; sidecars are in `/tmp/pricefixed-dob-capture/1082869/ocr/`

## Captured certificates

The C/O index listed the 1948 certificate plus 22 temporary amendments. All 23
were captured. The old certificate names the `272-278` First Avenue range;
the amendments' face address is `274 FIRST AVENUE`, while the permissible-use
section identifies all four address sections.

| Certificate set | SHA-256 coverage | Review result |
| :--- | :--- | :--- |
| `M000034154.PDF` | `c256d8a63c6322f531f0e8cd7a908174a9947ee465e303a99711c897748f82e9` | 1948 certificate for the 272–278 First Avenue range; identifies Unit #1–#4 sections and eight apartments per story, but no apartment labels. |
| `121333958-01.PDF` | `dd395fddfae6c3a7ca993ead51dcd8771f27b0f3bcda8232ea321b9d8f6654b4` | 2016 temporary certificate; face says 274 First Avenue and 416 dwelling units. Unit #1 (278), #2 (274), #3 (276), and #4 (272) are sections with seven/eight apartments per floor, not apartment identities. |
| `121333958-02.PDF` through `121333958-22.PDF` | Individual hashes and raw PDFs are retained in the capture directory. | Twenty-one later amendments repeat the same section-level occupancy structure; OCR found no apartment label such as `5A` or `12-4`. |

## Finding

The certificate's `UNIT #1`–`UNIT #4` values are building/occupancy sections
mapped to street-address ranges. The accompanying apartment values are counts
per floor. They do not identify individual apartments, so they remain
capacity/history evidence only. No canonical units were added.
