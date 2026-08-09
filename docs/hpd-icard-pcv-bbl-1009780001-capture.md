# HPD historical-card inventory: Peter Cooper Village BBL

This is a bounded source review for the 21 HPD building records returned for
BBL `1009780001` (block `978`, lot `1`). It does not merge the records into a
single address and does not create canonical units.

- Retrieval date: 2026-08-09 UTC
- HPD public search endpoint: `https://mspwvw-hpdleov3.nyc.gov/hpdonline.api/1.0/api/building/search`
- Search body: `{"boro":1,"block":978,"lot":1,"isCountRequired":true}`
- Historical-card endpoint pattern: `https://mspwvw-hpdleov3.nyc.gov/hpdonline.api/1.0/api/building/historicimage/list/{building_id}`
- Raw inventory: `/tmp/pricefixed-hpd-capture/1009780001/historic-card-inventory.json`
- Captured files and manifests: `/tmp/pricefixed-hpd-capture/1009780001/cards/{building_id}/`
- OCR sidecars: `/tmp/pricefixed-hpd-capture/1009780001/cards/{building_id}/ocr/`

## Inventory result

HPD returned 21 distinct building IDs. Eighteen buildings exposed one public
historical card each; three exposed none:

- `804841` — 360 1 Avenue, BIN 1083681
- `804842` — 370 1 Avenue, BIN 1083685
- `804844` — 390 1 Avenue, BIN 1083682

The 18 captured cards total 93 PDF pages. Their source references, HPD
document IDs, and checksums are preserved in each per-building manifest. The
card-to-building mapping is:

| HPD building ID | HPD premise | card source reference | document ID |
| ---: | :--- | :--- | ---: |
| 576 | 350 1 Avenue | `hpd-icard:576:606251` | 3594781 |
| 804382 | 431 East 20 Street | `hpd-icard:804382:598840` | 3541721 |
| 804383 | 441 East 20 Street | `hpd-icard:804383:598841` | 3541727 |
| 804386 | 511 East 20 Street | `hpd-icard:804386:598846` | 3541752 |
| 804389 | 531 East 20 Street | `hpd-icard:804389:598849` | 3541773 |
| 804390 | 541 East 20 Street | `hpd-icard:804390:598850` | 3541779 |
| 804391 | 601 East 20 Street | `hpd-icard:804391:598851` | 3541785 |
| 804401 | 420 East 23 Street | `hpd-icard:804401:597711` | 3533590 |
| 804402 | 440 East 23 Street | `hpd-icard:804402:597712` | 3533594 |
| 804403 | 510 East 23 Street | `hpd-icard:804403:597713` | 3533598 |
| 804404 | 530 East 23 Street | `hpd-icard:804404:597714` | 3533606 |
| 805218 | 2 Peter Cooper Road | `hpd-icard:805218:613993` | 3642856 |
| 805219 | 3 Peter Cooper Road | `hpd-icard:805219:613994` | 3642861 |
| 805220 | 4 Peter Cooper Road | `hpd-icard:805220:613995` | 3642863 |
| 805221 | 5 Peter Cooper Road | `hpd-icard:805221:613997` | 3642866 |
| 805222 | 6 Peter Cooper Road | `hpd-icard:805222:613998` | 3642869 |
| 805223 | 7 Peter Cooper Road | `hpd-icard:805223:613999` | 3642874 |
| 805224 | 8 Peter Cooper Road | `hpd-icard:805224:614000` | 3642877 |

## Review finding

The OCR-visible cards are classification, legal-occupancy, alteration, and
certificate-history records. They repeatedly expose building-level fields such
as `Class "A" Apartments`, `Rooms per Apartment`, `LEGAL OCCUPANCY`, and total
apartment counts. They do not provide an apartment roster. The visible `UNIT`
field on several forms is a blank form field, not a filled apartment label;
application numbers and certificate numbers beside it are document identifiers,
not unit identities.

No canonical units were added. The 18 cards are exact HPD-building-linked
historical observations, but their apartment totals remain capacity/history
evidence. The three buildings without cards remain an explicit source gap.

## Reproduction

The reusable capture tool accepts repeated building IDs and writes one raw card
list, PDF, and provenance manifest per building:

```bash
python3 tools/merges/capture_hpd_historic_images.py \
  --building-id 576 \
  --building-id 804382 \
  --building-id 804383 \
  --out-dir /tmp/pricefixed-hpd-capture/1009780001/cards
```

For the complete BBL inventory, use the 21 IDs in the raw search output. The
tool preserves source URLs, HPD identifiers, retrieval timestamps, and SHA-256
checksums and performs no unit extraction.
