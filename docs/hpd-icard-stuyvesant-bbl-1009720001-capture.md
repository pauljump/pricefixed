# HPD historical-card inventory: Stuyvesant Town BBL

This is a bounded source review for the HPD records returned for BBL
`1009720001` (block `972`, lot `1`). HPD returns multiple building records on
the tax lot, including legacy/duplicate records and addresses outside the
current Stuyvesant Town target footprint. Those identities remain separate.

- Retrieval date: 2026-08-09 UTC
- BBL: `1009720001` (Manhattan block `972`, lot `1`)
- HPD public search endpoint: `https://mspwvw-hpdleov3.nyc.gov/hpdonline.api/1.0/api/building/search`
- Search body: `{"boro":1,"block":972,"lot":1,"isCountRequired":true}`
- Raw inventory: `/tmp/pricefixed-hpd-capture/1009720001/historic-card-inventory.json`
- Captured files and manifests: `/tmp/pricefixed-hpd-capture/1009720001/cards/{building_id}/`
- OCR sidecars: `/tmp/pricefixed-hpd-capture/1009720001/cards/{building_id}/ocr/`

## Inventory result

The search returned 46 HPD building records. Twenty-eight records exposed one
or more cards, yielding 29 PDFs and 177 pages. Eighteen records exposed no
card, including the following duplicate/legacy or outside-footprint records:

`804360` (435 East 14 Street), `804833` (270 1 Avenue), `804834` (272 1
Avenue), `804835` (280 1 Avenue), `804836` (300 1 Avenue), `804837` (310 1
Avenue), `804838` (400 East 20 Street), `955137` (435 East 14 Street),
`955143` (400 East 20 Street), `955145` (270 1 Avenue), `975665` (254 1
Avenue), `994139` (330 East 55 Street), `995425` (259 West 146 Street),
`997027` (245 Avenue C), `997028` (528 Garage East 20 Street), `997029` (330
1 Avenue), `997030` (409 East 14 Street), and `997031` (629 East 14 Street).

Every captured card has a per-building manifest containing its HPD building ID,
card sequence, document ID, source URL, retrieval time, and SHA-256 checksum.
The aggregate checksum list is at
`/tmp/pricefixed-hpd-capture/1009720001/card-checksums.tsv`.

## Review finding

The cards contain historical classification, occupancy, alteration, and
certificate information. Several Stuyvesant Town cards visibly/OCR-wise refer
to `Unit #1`, `Unit #2`, `Unit #3`, or ranges such as `Unit 1-2 to 13`. In
context these are building/occupancy-section identifiers accompanied by totals
such as `103 Apts.` or `119 Apts.`; they are not apartment labels like `5A`,
`12-4`, or a floor-by-floor roster. The forms also contain blank `UNIT` fields.

No individual apartment identities were observed in the bounded OCR review.
The source therefore contributes exact HPD-building-linked historical
observations and capacity context only. No canonical units were added, and no
Peter Cooper Village evidence was carried across to this BBL.

## Reproduction

The reusable capture tool accepts repeated HPD building IDs and writes one raw
card list, PDF, and provenance manifest per building:

```bash
python3 tools/merges/capture_hpd_historic_images.py \
  --building-id 535 \
  --building-id 804067 \
  --building-id 804068 \
  --out-dir /tmp/pricefixed-hpd-capture/1009720001/cards
```

The complete 46-ID invocation is represented by the raw search output and can
be regenerated from its `hpd-buildings.tsv` file. The tool performs no unit
extraction or canonical import.
