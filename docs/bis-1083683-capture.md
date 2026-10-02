# BIS certificate capture: BIN 1083683

This is the certificate review record for queue target `400 E 23 ST`,
captured on 2026-08-08.

- BIS profile premise: `400 EAST 23 STREET MANHATTAN 10010`
- BIN: `1083683`
- BIS block/lot and BBL: `978 / 1` and `1009780001`
- C/O index: `https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=1&allbin=1083683`
- C/O premise: `400 EAST 23 STREET MANHATTAN`
- Extraction method: Poppler `pdftoppm` at 300 DPI, then local Apple Vision
  (`VNRecognizeTextRequest`, accurate mode) through
  `tools/merges/ocr_dob_pdf_macos.swift`

| Source reference | Public document URL | SHA-256 | Review finding |
| :--- | :--- | :--- | :--- |
| `bis-co:1083683:M000021666.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=021000&cofomatadata5=M000021666.PDF` | `e8c651e277d3973b07ee1e051613cca098015cc75e248117334ad9a05b651a5c` | Scanned face identifies block 954 and a different business premise; no apartment labels. |
| `bis-co:1083683:M000026088.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=026000&cofomatadata5=M000026088.PDF` | `a345daba92e2a58876be628b9e08c97d5f9b198ca6c93d88b03a2122902a8e6a` | Scanned face identifies a different West 23rd Street premise; no apartment labels. |
| `bis-co:1083683:M000021500.PDF` | `https://a810-bisweb.nyc.gov/bisweb/CofoDocumentContentServlet?passjobnumber=null&cofomatadata1=COFO&cofomatadata2=M&cofomatadata3=000&cofomatadata4=021000&cofomatadata5=M000021500.PDF` | `e8db04d26692d3263aa11374f13e01cb5362c126b495fb4a21d78fabadacc8c6` | Scanned face identifies block 954 and a different business premise; no apartment labels. |

No canonical units were added. The documents are retained as source-level
identity checks and rejected/ambiguous evidence, not apartment records.
