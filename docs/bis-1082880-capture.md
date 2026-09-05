# BIS certificate capture: BIN 1082880 / 447 East 14 Street

This is a targeted DOB document review for a Stuyvesant Town address. It is
source evidence only; no canonical units were imported.

- Retrieval: 2026-08-08 ET / 2026-08-09 UTC
- BIS property profile: `https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet?bin=1082880`
- C/O index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=0&allbin=1082880`
- BIS premise: `447 EAST 14 STREET MANHATTAN`
- BIN: `1082880`
- Block/lot: `972/1`
- BBL: `1009720001`
- Local capture directory: `/tmp/pricefixed-dob-capture/1082880/`
- OCR method: local Apple Vision helper; sidecars are in `/tmp/pricefixed-dob-capture/1082880/ocr/`

## Captured certificates

| Certificate | SHA-256 | Review result |
| :--- | :--- | :--- |
| `M000034284.PDF` | `09033751e05f8f47881906e6af79f520c21e652fd1a4ba373df1c79792fd3521` | Face identifies 416 Eighth Avenue / 258–262 West 31st Street, block 780 lot 73; identity conflict, rejected for this target. |
| `M000035592.PDF` | `c45f70fcbd025692ae5effd44f732663c6cf7de39a4f860f4ef5ca5fecb69b4e` | Face identifies 447–455 East 14 Street, block 972 lot 1; legal occupancy lists Unit #2 and 7/8 apartments per story, but no apartment labels. |
| `M000037744.PDF` | `c4551abd532a855c74db608c57196a9deac7a171ad3c77e54eba04cde71dcd25` | Block 972 lot 1 and five numbered building sections are visible in OCR; the PDF text did not expose an exact street address or apartment labels. |

The index's public document endpoint is reconstructed from the three BIS form
records. The captured PDFs are retained outside the repository with their
original BIS filenames; the generic browser download names are not used as
source identifiers.

## Finding

The `UNIT #1`–`UNIT #5` references in these certificates are building or
occupancy-section identifiers accompanied by counts such as seven or eight
apartments per story. They are not apartment labels such as `5A` or `12-4`,
and the records do not provide a floor-by-floor apartment roster. The one
certificate with a clean exact premise is therefore capacity/history evidence
only. No canonical units were added.

The deterministic DOB PDF parser keeps this distinction explicit: occupancy
section identifiers and count rows remain `no_explicit_unit_label` rather than
becoming review candidates for import.
