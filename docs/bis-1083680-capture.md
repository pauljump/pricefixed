# BIS certificate capture: BIN 1083680

This is the duplicate-controlled review record for the next unresolved queue
target, `348 1 AVENUE`, captured on 2026-08-08.

- BIS profile queried: `348 1 AVENUE MANHATTAN 10010`
- BIN: `1083680` (BIS marks the BIN obsolete)
- BIS profile block/lot and BBL: `978 / 1` and `1009780001`
- C/O index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=1&allbin=1083680`
- C/O index premise: `350 FIRST AVENUE MANHATTAN`
- Relationship to target: shared BBL, different official premise; no exact-address
  apartment evidence
- Extraction method: Poppler `pdftoppm` at 300 DPI, then local Apple Vision
  (`VNRecognizeTextRequest`, accurate mode) through
  `tools/merges/ocr_dob_pdf_macos.swift`

| Source reference | Public document URL | SHA-256 | Review finding |
| :--- | :--- | :--- | :--- |
| `bis-co:1083680:M000020125.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=020000&cofomatadata5=M000020125.PDF` | `7adb2ab78eac39d53ba70bcd0826ca1162a093e21bc28b4ec14c76919b5ffc8f` | Scanned face identifies block 953 and a different Avenue A premise; business-use certificate, no apartment labels. |
| `bis-co:1083680:M000005191.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=005000&cofomatadata5=M000005191.PDF` | `b0f8b7514e7fa32e278bee4f0aca4f6ebe0b1b04db386ee3f0ee568be815e9d9` | Scanned face identifies block 980 and different East 22nd/23rd Street premises; business-use certificate, no apartment labels. |

No canonical units were added. These documents remain shared-BBL or
document-identity-conflict evidence and do not justify copying apartment
labels, counts, or patterns to `348 1 AVENUE` or any other address.
