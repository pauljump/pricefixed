# DOB document capture workflow

This workflow bridges the gap between BIS pages that work in a normal browser
and the PDFs that the unattended command-line client cannot retrieve. It is a
document-acquisition and review workflow, not a unit generator.

## Capture one property

1. Start from the exact `bis_property_profile_url` in the generated queue.
2. Confirm the BIS profile's displayed premise, borough, block, and lot. Do not
   assume the queued BBL is correct just because the address text matches.
3. Open **View Certificates of Occupancy** and save that certificate-index page
   as HTML, retaining the exact URL shown in the browser.
4. Open each `M...PDF` certificate link and download the PDF with its original
   filename. Keep the original file; do not rename it to a guessed address.
5. Build a manifest from the saved index page:

```bash
python3 tools/merges/prepare_dob_document_manifest.py \
  --index-html /path/to/bis-co-index.html \
  --index-url 'https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?...' \
  --targets /tmp/stuytown-unit-document-targets-all-sources.csv \
  --pdf-dir /path/to/dob-pdfs \
  --out /tmp/stuytown-dob-document-manifest.csv
```

The manifest reconstructs the public PDF endpoint from the form's hidden
fields and joins it to queued targets. It labels each relationship as
`exact_premise`, `shared_bbl`, or `bbl_mismatch`.

## Review captured PDFs

Run the deterministic text pass after the PDFs are saved:

```bash
python3 tools/merges/extract_dob_pdf_candidates.py \
  --manifest /tmp/stuytown-dob-document-manifest.csv \
  --out /tmp/stuytown-dob-pdf-candidates.csv
```

The output is still review-only. A `review_candidate` row means that the PDF
text contains the target address and an explicit apartment/unit marker. A
`shared_bbl_candidate` row is retained for investigation but cannot establish
that the label belongs to the target address. `bbl_mismatch` rows are identity
conflicts and cannot be imported.

Many older certificates are image-only scans, so `pdftotext` may return no
useful text. On macOS, create a same-stem OCR sidecar with the checked-in local
Apple Vision helper:

```bash
swift tools/merges/ocr_dob_pdf_macos.swift \
  /path/to/dob-pdfs/M000034595.PDF \
  /path/to/dob-ocr/M000034595.txt

python3 tools/merges/extract_dob_pdf_candidates.py \
  --manifest /tmp/stuytown-dob-document-manifest.csv \
  --text-dir /path/to/dob-ocr \
  --out /tmp/stuytown-dob-pdf-candidates.csv
```

The extractor prefers a same-stem sidecar and falls back to `pdftotext` when
one is absent. OCR is discovery/review text only. Do not create a canonical
unit from an OCR count, a floorplan pattern, or an uncertain OCR label; review
the original PDF and preserve its exact address, BBL, source reference, URL,
retrieval date, and checksum. Browser downloads may use a generic filename,
so retain the original downloaded file as well as the source filename recorded
in the BIS index manifest.

The final reviewed CSV must still contain the strict importer fields:
`address`, `bbl`, `unit_label`, `source_ref`, `source_url`, and `observed_at`.
Only then may it be passed to `import_unit_labels.py`.

## Why the BBL check is mandatory

During live validation, the BIS profile for `342 1 AVENUE` displayed BIN
1082865, block 972, lot 1 (`1009720001`). The complex queue also contains a
Peter Cooper Village row for the same address normalized to BBL `1009780001`.
The manifest marks that row `bbl_mismatch`; it does not let matching address
text override the authoritative tax-lot identity.
