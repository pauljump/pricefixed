# HPD historical I-card capture: 350 1 Avenue

This is a source review record, not a unit import.

- Retrieval date: 2026-08-09 (UTC)
- Official HPD Online building page: `https://hpdonline.nyc.gov/hpdonline/building/576`
- Historical-card page: `https://hpdonline.nyc.gov/hpdonline/building/576/historical`
- HPD building ID: `576`
- Premise shown by HPD: `350 1 Avenue, Manhattan, 10010`
- Identity crosswalk: block `978`, lot `1`; BBL `1009780001`
- Card listed by HPD: `Icard_606251.pdf`, dated `02/15/2008`, description `I-CARD IMAGE(S)`
- API source reference: `hpd-icard:576:606251`
- Metadata endpoint: `https://mspwvw-hpdleov3.nyc.gov/hpdonline.api/1.0/api/building/historicimage/list/576`
- Document endpoint: `https://mspwvw-hpdleov3.nyc.gov/DocService/v1/api/documents/content/606251/3594781/53/73`
- Captured PDF: `/tmp/pricefixed-hpd-capture/576/Icard_606251.pdf`
- SHA-256: `0f24c82476787f9aee4d914fb110b73ca5bb862df906f1418f779a1266da8a27`
- Size: 9 pages, 5,252,653 bytes
- Extraction: checked-in OCR workflow using local Apple Vision helper; raw OCR sidecar at `/tmp/pricefixed-hpd-capture/576/ocr/Icard_606251.txt`

## Finding

The card is exact-address and exact-BBL historical evidence for the property,
but it records building history, legal occupancy, and apartment counts rather
than apartment identities. The OCR-visible pages include `350 1 Avenue`,
`Peter Cooper Village`, block `978`, lot `1`, and historical apartment totals
(`114`, `116`, and `119` appear in different dated cards). No apartment/unit
labels tied to individual premises were observed.

Therefore this capture does **not** create canonical units. The counts remain
capacity/history evidence only. The PDF is retained for later human review if
another source supplies an apartment label that can be cross-checked against
this property history.

## Reproduction

Capture the public card and its provenance with:

```bash
python3 tools/merges/capture_hpd_historic_images.py \
  --building-id 576 \
  --out-dir /tmp/pricefixed-hpd-capture/576 \
  --doc-id 3594781
```

The tool writes the raw card-list JSON, the PDF, and a manifest containing the
source identifiers, URLs, retrieval time, and checksum. It does not parse or
import unit labels.
