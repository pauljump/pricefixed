# BIS certificate capture: BIN 1082885 / 521 East 14 Street

This is a targeted DOB document review for a Stuyvesant Town address. It is
source evidence only; no canonical units were imported.

- Retrieval: 2026-08-08 ET / 2026-08-09 UTC
- BIS property profile: `https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet?bin=1082885`
- C/O index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=0&allbin=1082885`
- BIS premise: `521 EAST 14 STREET MANHATTAN`
- BIN: `1082885`
- Block/lot: `972/1`
- BBL: `1009720001`
- Local capture directory: `/tmp/pricefixed-dob-capture/1082885/`
- OCR method: local Apple Vision helper; sidecars are in `/tmp/pricefixed-dob-capture/1082885/ocr/`

## Captured certificates

| Certificate | SHA-256 | Review result |
| :--- | :--- | :--- |
| `M000033888.PDF` | `468d8bacb3f3e873493e85df187b3c053f2f81f385bb8d3ec9ef3cfb1a93d2a1` | Exact 521–525 East 14th Street certificate for Building 21, Units 1–3; seven/eight apartments per story, no apartment labels. |
| `M000034949.PDF` | `07f4a524adda26f1de7d9f7deee982d2a428db603c66c422bf4a8cc48cafe1b5` | Amendment superseding the exact 521–525 East 14th Street certificate; repeats section-level counts, no apartment labels. |
| `M000033883.PDF` | `1767a74455261cf67c82447fd965ffef0d3a409aef606e212de4d34ae848bcfb` | Identity conflict: 40 Elizabeth Street, block 203 lot 3; rejected for this target. |
| `M000033912.PDF` | `2ffda4e6c925c13e2da266a4c58521ed84f1065f5c5f9f45ccd6fd961584441d64` | Garage certificate for blocks 946–951; not an apartment roster and not exact target evidence. |
| `M000036926.PDF` | `d510974d0da1e4146c4f0248339c6fe0058e404301d35fc5a586f4be2dbede6f` | 527 East 14 Street garage certificate; not an apartment roster or exact 521 address evidence. |

## Finding

The exact 521–525 certificates identify numbered building sections and
per-story apartment counts only. The other three records demonstrate why the
BIN/premise check matters: the same public index can expose neighboring or
unrelated scans. No canonical units were added.
