# BIS certificate capture: BIN 1082886 / 627 East 14 Street

This is a targeted DOB document review for a Stuyvesant Town address. It is
source evidence only; no canonical units were imported.

- Retrieval: 2026-08-08 ET / 2026-08-09 UTC
- BIS property profile: `https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet?bin=1082886`
- C/O index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=0&allbin=1082886`
- BIS index premise: `627 EAST 14 STREET MANHATTAN`
- BIN: `1082886`
- Block/lot: `972/1`
- BBL: `1009720001`
- Local capture directory: `/tmp/pricefixed-dob-capture/1082886/`
- OCR method: local Apple Vision helper; sidecars are in `/tmp/pricefixed-dob-capture/1082886/ocr/`

## Captured certificates

The index listed one temporary certificate and ten later temporary amendments.
All eleven were captured. The face of each certificate identifies `629 EAST
14TH STREET`, BIN `1082771`, rather than the index premise `627 EAST 14
STREET` / BIN `1082886`; that address/BIN discrepancy is retained and prevents
an exact-address import for 627 East 14 Street.

| Certificate | SHA-256 | Review result |
| :--- | :--- | :--- |
| `121203857T001.PDF` | `154cb64beb1cec9ef95c7a369629b2858beb15120b3f99b7bd1de89fb6100407` | Temporary certificate dated 2018-10-03; face says 629 East 14th Street and one dwelling unit, with no apartment labels. |
| `121203857-11.PDF` | `65c5100172ae61119d637f310fc720e9734b0107194f0e902fd1a63608d32a12` | 2021 temporary amendment for 629 East 14th Street; no apartment labels. |
| `121203857-10.PDF` | `a74a23c72f6b72771b33d2c2587bdf07ccb47f325c10e11fa2351e65af05b335` | 2020 temporary amendment; no apartment labels. |
| `121203857-09.PDF` | `7554e507db06c1f47eefac8baa815fb618dc83ba530c1830aea4b164c4a9d78d` | 2020 temporary amendment; no apartment labels. |
| `121203857-08.PDF` | `cadf43654a9aaf9e62f6a473fab584b7a47c7bae89c88457888509d0a1084255` | 2020 temporary amendment; no apartment labels. |
| `121203857-07.PDF` | `ea30a6b6ebfc79d92e852546ebc75d19d5dd6976ef85d39d35898e60e72cd318` | 2020 temporary amendment; no apartment labels. |
| `121203857-06.PDF` | `d683c31584dfe047adfa224c2568f5945b11db19fba918eeb76f022aa7892138` | 2019 temporary amendment; no apartment labels. |
| `121203857-05.PDF` | `21b679c8927c7647a2e8eb1ad975b039f806c4aa0c99283c5a2122dc95a97e39` | 2019 temporary amendment; no apartment labels. |
| `121203857-04.PDF` | `0f6515d737a237eb1014231ea4283155bdf908073ce83214fbdf26aed9f7a787` | 2019 temporary amendment; no apartment labels. |
| `121203857-03.PDF` | `2c64c76b71757ebebbc43d36b9924caa43cd679d6c01991d0947b90fbec5bf27` | 2019 temporary amendment; no apartment labels. |
| `121203857-02.PDF` | `8f43d78c5ca6eb7a78ef3ceb22af288b2167d331d22f038a4b10abf495b0c1dd` | 2018 temporary amendment; no apartment labels. |

## Finding

The certificates describe a temporary accessory fitness-center occupancy, not
an apartment roster. Their `APARTMENTS` text is a general use description and
does not identify individual units. Because the certificate face also names
629 East 14 Street / BIN 1082771 while the index was opened for 627 East 14
Street / BIN 1082886, these records remain shared-BBL capacity/history evidence
only. No canonical units were added.
