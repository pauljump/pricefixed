"""Rent Stabilization — the signal NYC Open Data doesn't publish directly.

There is no Socrata dataset of "which BBLs are rent-stabilized." DHCR (the state
agency that actually knows) does not publish a public, bulk, machine-readable feed —
you can look up one building at a time on the DHCR website, but there's no API. The
closest thing NYC has to a bulk, address-level answer comes from a community project,
not a city agency:

`taxbills.nyc` / `nyc-stabilization-unit-counts` (github.com/talos/nyc-stabilization-unit-counts,
by John Krauss / BetaNYC, later folded into JustFix's tooling): NYC property tax bills
carry a "Housing-Rent stabilization" line with a unit count and, separately, whether the
building claims a J-51 or 421-a tax abatement (both of which *require* rent stabilization
as a condition of the benefit). The project bulk-downloaded and OCR'd/parsed years of DOF
tax bill PDFs into a flat CSV, hosted on S3 under a CC BY-SA license. This is GROUND
TRUTH — it's literally what landlords told the city on their own tax filings — not a
proxy, for the buildings it covers.

We pull `changes-summary.csv`, a small (~46k row) one-row-per-BBL rollup of that scrape:

    https://taxbillsnyc.s3.amazonaws.com/changes-summary.csv

Columns we use: ucbbl (10-digit BBL), unitsstab2017 (the most recent stabilized-unit
count the scrape captured), j51 / a421 (the abatement window, e.g. "2010 - 2017", when
the tax bill shows one of those benefits in force).

*** THE HONEST CAVEAT, READ THIS BEFORE TRUSTING A ROW ***
This project stopped scraping after the 2017 tax year — the header column is literally
named `unitsstab2017`, not a live year. As of 2026 this is a NINE-YEAR-OLD snapshot.
Worse: the 2019 Housing Stability and Tenant Protection Act (HSTPA) eliminated most of
the paths landlords used to deregulate stabilized units (high-rent/high-income vacancy
decontrol), so post-2019 reality skews MORE buildings stabilized than this 2017 snapshot
shows, not fewer. Treat every row here as "was stabilized as of 2017," never as "is
stabilized today." We surface `rent_stab_year` on every row precisely so a consumer
can't mistake this for a live signal.

Two-tier signal per BBL, both from the SAME file (so we never had to reach for the
J-51/421-a NYC Open Data proxy separately — the tax-bill scrape already carries both
the ground-truth unit count AND the abatement flags in one row):

  - "registered"   — a real DHCR-derived unit count > 0 was on the 2017 tax bill.
                      `rent_stab_units` is set to that count.
  - "j51-proxy" /
    "421a-proxy"    — no direct unit count, but the same tax bill shows a J-51 or 421-a
                      abatement in force (both require stabilization as a condition of
                      the benefit) — a PROXY, not a headcount. `rent_stab_units` is left
                      NULL; we never invent a unit count from an abatement flag.
  - no row written  — the tax-bill scrape shows neither signal for that BBL. Silence,
                      not a claim of "not stabilized" (the scrape only covered 6+ unit
                      buildings and HCR-listed buildings, so smaller buildings are
                      genuinely absent, not confirmed unstabilized).

No third-party dependencies. Python 3.9+ standard library only — this is a flat CSV
over plain HTTPS, so no Socrata pagination is needed; the whole file is one `fetch()`.
"""
from __future__ import annotations

import csv
import io

from ..core import fetch
from .core import RecordSource, upsert_building

CSV_URL = "https://taxbillsnyc.s3.amazonaws.com/changes-summary.csv"

# The scrape's last covered tax year — literally the suffix on the CSV's own column
# name (`unitsstab2017`). Verified 2026-07 by fetching the live header; if the source
# is ever refreshed with a later year this constant (and the column name below) is the
# one place to bump.
SNAPSHOT_YEAR = 2017
UNIT_COUNT_COL = f"unitsstab{SNAPSHOT_YEAR}"


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


class RentStabilizationSource(RecordSource):
    name = "rent_stabilization"
    description = (
        "taxbills.nyc DHCR-derived stabilized-unit counts (2017 snapshot) "
        "+ J-51/421-a abatement proxy — see module docstring for vintage caveat"
    )

    def pull(self, conn, limit=None):
        try:
            text = fetch(CSV_URL)
        except Exception as e:  # noqa: BLE001 — fail loud, never fabricate a row
            raise RuntimeError(
                f"rent_stabilization: could not reach the taxbills.nyc CSV at "
                f"{CSV_URL} ({e}). This source has no fallback — DHCR itself publishes "
                f"no bulk API, so without this community scrape we have NO rent-"
                f"stabilization signal to offer. Returning nothing rather than "
                f"guessing."
            ) from e

        reader = csv.DictReader(io.StringIO(text))
        if UNIT_COUNT_COL not in (reader.fieldnames or []):
            raise RuntimeError(
                f"rent_stabilization: expected column {UNIT_COUNT_COL!r} not found in "
                f"the CSV header ({reader.fieldnames!r}). The upstream file's schema "
                f"has likely moved past our verified {SNAPSHOT_YEAR} snapshot — update "
                f"SNAPSHOT_YEAR rather than silently pulling the wrong column."
            )

        n = 0
        registered = proxy_j51 = proxy_421a = skipped = 0
        for row in reader:
            if limit is not None and n >= limit:
                break
            bbl = (row.get("ucbbl") or "").strip()
            if len(bbl) != 10 or not bbl.isdigit():
                continue

            stab = _int(row.get(UNIT_COUNT_COL))
            j51 = (row.get("j51") or "").strip()
            a421 = (row.get("a421") or "").strip()

            fields = {"rent_stab_year": SNAPSHOT_YEAR}
            if stab and stab > 0:
                fields["rent_stab_units"] = stab
                fields["rent_stab_status"] = "registered"
                registered += 1
            elif j51:
                fields["rent_stab_status"] = f"j51-proxy ({j51})"
                proxy_j51 += 1
            elif a421:
                fields["rent_stab_status"] = f"421a-proxy ({a421})"
                proxy_421a += 1
            else:
                skipped += 1
                continue  # no signal at all — write nothing rather than a blank row

            upsert_building(conn, bbl, fields)
            n += 1

        conn.commit()
        print(
            f"  {registered} registered (real {SNAPSHOT_YEAR} DHCR unit counts), "
            f"{proxy_j51} J-51 proxy, {proxy_421a} 421-a proxy, "
            f"{skipped} rows with no stabilization signal skipped"
        )
        return n


if __name__ == "__main__":
    # Live demo: pull a sample straight into a scratch db and show real rows. This
    # source alone doesn't populate `address` (that's PLUTO's job), so the demo joins
    # nothing else in — just proves the pull + upsert against the live S3 file.
    import sys

    from .core import init_record_db

    conn = init_record_db(sys.argv[1] if len(sys.argv) > 1 else "rent_stab_demo.db")
    src = RentStabilizationSource()
    src.run(conn, limit=500)
    print("\n  sample rows (bbl -> units, status, year):")
    for bbl, units, status, year in conn.execute(
        "SELECT bbl, rent_stab_units, rent_stab_status, rent_stab_year "
        "FROM buildings ORDER BY rent_stab_units DESC LIMIT 10"
    ):
        print(f"    {bbl}  units={units}  status={status!r}  year={year}")
