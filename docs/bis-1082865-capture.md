# BIS certificate capture: BIN 1082865

This is the durable review record for the browser-assisted capture performed
on 2026-08-08. It records the public source references and checksums without
turning scanned occupancy counts into apartment records.

- BIS certificate index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=1&allbin=1082865`
- BIS header premise: `330 1 AVENUE MANHATTAN`
- BIN: `1082865`
- BIS block/lot and BBL: `972 / 1` and `1009720001`
- Extraction method: Poppler `pdftoppm` at 300 DPI, then local Apple Vision
  (`VNRecognizeTextRequest`, accurate mode) through
  `tools/merges/ocr_dob_pdf_macos.swift`
- Review output: 880 target-document rows, all
  `shared_bbl_no_explicit_unit_label`; no canonical units added

The original browser downloads are retained outside the repository. Their
source filenames, public document URLs, and SHA-256 checksums are:

| Source reference | Public document URL | SHA-256 |
| :--- | :--- | :--- |
| `bis-co:1082865:M000034595.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=034000&cofomatadata5=M000034595.PDF` | `574ffbff758927e20121e5c9b8e8e3bac6d72d12b699d4555720809ceb9561c2` |
| `bis-co:1082865:M000035795.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=035000&cofomatadata5=M000035795.PDF` | `51c08baf5f623869a3f7391bcbd4d1573eab1a0b052b42011509cbdd2f456b55` |
| `bis-co:1082865:M000040059.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=040000&cofomatadata5=M000040059.PDF` | `06bdcdc4f5c1aea3689488a1a6a3f5d57e90d3fc49de018ac09528c40d5e2226` |
| `bis-co:1082865:M000028093.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=028000&cofomatadata5=M000028093.PDF` | `e091a0f556b91aa039240bf82ae436f5b9112fd09ae54142c3c2af06a88f9cf7` |

The first three scans identify building/unit groupings and occupancy counts,
but do not enumerate apartment labels. The fourth scan's face says `332 First
Avenue`, block 951 lot 3, conflicting with the BIS header. It remains an
identity conflict. Counts, OCR text, and the shared BBL are retained as review
evidence only.
