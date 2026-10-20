# DOB Schedule A bulk release (FOIL-2026-810-05483)

The Certificate of Occupancy occupancy table (Schedule A: floor, use, dwelling or rooming
units, maximum persons) is not published on NYC Open Data. The Open Data CO sets carry one
dwelling-unit total per certificate. We asked DOB for the table in bulk under FOIL.

## The request

Filed 2026-09-28 on NYC OpenRecords, agency Department of Buildings. Text:

```text
Under FOIL, I request an electronic copy of the Certificate of Occupancy data maintained in BIS
and DOB NOW, including the floor-by-floor occupancy table shown on each certificate (for example:
floor, permitted use, number of dwelling units, rooming units, and maximum persons), along with
the certificate details (BIN, BBL, address, job number, CO number, type, and issue date).

I'm requesting this for all certificates available in electronic form. An existing database
export, extract, or report in CSV or Excel is fine, and separate files for BIS and DOB NOW are
fine. I am not requesting the PDF images of the certificates.

If fees apply, please let me know the estimate before processing. If any part is withheld, please
release the remainder.
```

DOB estimated a response by 2027-01-05 and fulfilled it on 2026-10-20, with no fee.

## What DOB released

Six Excel files, released to the requester (not posted on the portal):

| File | Rows | What it is |
|---|---:|---|
| `BIS_-_ScheduleA_co_20261016.xlsx` | 935,613 | BIS Schedule A, one sheet per borough, COs from about 1989 to 2021 |
| `DOBNOW-ScheduleA-20261016.xlsx` | 285,242 | DOB NOW Schedule A, 2021 on, one sheet per borough |
| `BIS-DOB_Certificate_Of_Occupancy_20261008.xlsx` | 143,218 | BIS CO list; same content as Open Data `bs8b-p36w` |
| `DOB_NOW__Certificate_of_Occupancy_20261008.xlsx` | 82,710 | DOB NOW CO list; same content as the Open Data DOB NOW CO set |
| two data dictionaries | | BIS (2017-11-22) and DOB NOW CO field definitions |

The raw files are kept outside the repository.

## How the Schedule A files read

DOB did not document this; it was measured against each CO's own dwelling-unit total.

**BIS** (`Job Number, D_BIN, zoning use, floor from, floor to, max persons, dwelling/rooming
units, date`). Each floor range appears once per use, and the range's unit count is repeated
on every use row. A range row (for example floors 004 to 006) usually gives units per floor,
not the range total. The rule *smallest nonzero count per range, times the floors in the
range, summed over the job* matches the CO total exactly for 81% of 26,482 comparable jobs
and within 5% for 93%.

**DOB NOW** (`Job Filing, BIN, status, floor, floor number, occupancy group, max persons,
dwelling/rooming units`). The table is repeated once per filing (`-I1`, `-P1`, `-P2`, ...).
Most filings leave units blank: of 2,462 multifamily CO jobs, 690 list any unit count, and
only about 100 sum to the CO total. DOB NOW Schedule A is good for floor uses, weak for unit
counts.

## What it adds to the catalog

Schedule A gives **units per floor, never apartment labels**. Under the catalog contract it
cannot create a canonical unit. It is capacity and hypothesis evidence:

- 60,835 buildings (by BIN) get a floor plan from their latest CO that lists units.
- 53,812 of those plans agree within 5% with the building's expected unit count (HPD legal
  Class A count, else the CO total, else PLUTO for single-building lots).
- A reconciled plan can place an unnamed home on a floor (`floor 3, 1 of 8`) as a
  hypothesis, and can check a building's named labels against its floor layout. It does not
  name the home.

Buildings without a CO since about 1989, which includes most older walk-ups, have no
Schedule A at all.
