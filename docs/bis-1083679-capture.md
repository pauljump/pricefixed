# BIS certificate capture: BIN 1083679

This is the certificate review record for the queue target `352 1 AVENUE`,
captured on 2026-08-08.

- BIS profile premise: `352 1 AVENUE MANHATTAN 10010`
- BIN: `1083679`
- BIS block/lot and BBL: `978 / 1` and `1009780001`
- C/O index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=1&allbin=1083679`
- C/O premise: `350 1 AVENUE MANHATTAN`
- Relationship to target: shared BBL, different official premise
- Extraction method: Poppler `pdftoppm` at 300 DPI, then local Apple Vision
  (`VNRecognizeTextRequest`, accurate mode) through
  `tools/merges/ocr_dob_pdf_macos.swift`

| Source reference | Public document URL | SHA-256 | Review finding |
| :--- | :--- | :--- | :--- |
| `bis-co:1083679:104359542T001.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=104000&cofomatadata5=104359542T001.PDF` | `2c66d19112b25a2814d6615594ebf885b7692fa38b7236b8bb25f1180d047dec` | 2021 temporary C/O; 114 dwelling units; use table says two apartments and eight apartments per floor, but no apartment labels. |
| `bis-co:1083679:103787724T002.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=103&cofomatadata4=787000&cofomatadata5=103787724T002.PDF` | `29562a394679f2843f556bd620784b247d768f7e109718b78b0d39924969674e` | 2006 temporary C/O; 114 dwelling units; no apartment labels. |
| `bis-co:1083679:103787724T001.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=103&cofomatadata4=787000&cofomatadata5=103787724T001.PDF` | `ca5b2b807265e71a70782b51733a2ee8dae8b2ee1d58b275d8e73bfcc7695a7f` | 2006 temporary C/O; 114 dwelling units; no apartment labels. |
| `bis-co:1083679:103787724-08.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=103&cofomatadata4=787000&cofomatadata5=103787724-08.PDF` | `0f5e69661d9b02102b62cf389954016226e1a5078fe0bf2c9ce04a66eca5aaad` | 2018 temporary C/O; 114 dwelling units; no apartment labels. |

These records are useful dated capacity/use observations for the shared BBL,
not canonical apartment evidence. No units were added for `352 1 AVENUE` or
for `350 1 AVENUE`; the queue's 114-unit count remains separate from the
named-unit layer.
