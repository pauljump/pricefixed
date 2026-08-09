# Pricefixed handoff

Updated 2026-08-09 at the requested archive point.

## Repository state

- Repository: `/Users/mini-home/Desktop/unwalled`
- Branch: `agent/acris-backlog-runner`
- Latest commit: `ad86050 Document ranked ACRIS and Spherexx review`
- The tracked worktree is clean at this handoff. The unrelated
  `/Users/mini-home/Desktop/unwalled/soannoying/` directory was not touched.
- Local SQLite databases and caches are ignored build artifacts. Do not treat them
  as a committed release; verify their counts before relying on them.

## Mission and non-negotiable evidence rules

Pricefixed is building an open, traceable NYC housing catalog. A canonical unit may
be created only when a retained source supplies an explicit unit label tied to an
exact premise and a defensible BBL resolution. The core chain is:

```text
BBL / tax lot -> official premise address -> apartment or unit label -> dated observations
```

A BBL can contain multiple addresses. A BBL-wide label is therefore not valid for
every address on that lot. Keep exact-address evidence separate from shared-BBL
evidence. Building counts, floorplans, repeated patterns, and model guesses may be
stored as capacity or hypotheses, but never as fake canonical apartments.

The named-unit layer and the anonymous capacity layer are separate. PLUTO capacity
slots answer how many residential positions a source reports; they do not identify
apartments.

## Committed catalog position

The committed documentation currently reports:

- **3,052,376** canonical units with source-supplied labels and resolved BBLs.
- **3,753,223** anonymous PLUTO capacity slots.
- **3,705,000** NYC housing-stock reporting benchmark.
- Approximately **652,624** benchmark homes not yet represented by named,
  resolved canonical units.

These are deliberately different denominators. The remaining gap is a
source-acquisition problem, not permission to manufacture records.

## What is complete

Recent bounded, reproducible work is committed in this sequence:

- `15a4f59` — idempotent DOF unit-lot backlog.
- `443392a` — Mirador public GraphQL availability plus DOF address bridge.
- `084ea1a` — Related Rentals unit-detail feed.
- `9264de5` — LeFrak City Spherexx availability.
- `ad86050` — ranked ACRIS and Spherexx review documentation.

The repository already contains deterministic adapters for the shipped public
listing lanes, including StuyTown, TF Cornerstone, AvalonBay, SecureCafe,
AppFolio, MRI ProspectConnect, Nestio/Dermot, Rockrose, Rudin, Related Rentals,
Mirador, Spherexx, UDR, and the other entries in `FEEDS.md`.

## LeFrak City checkpoint

The Spherexx adapter in
[`pricefixed/adapters/spherexx.py`](pricefixed/adapters/spherexx.py) now covers
three confirmed portals: Marquis, Kings & Queens, and LeFrak City. The bounded
LeFrak pull found exactly two current explicit unit options:

- `8D` at `97-28 57th Avenue` (Panama)
- `4B` at `97-30 57th East Avenue` (United States)

The adapter joins public Spherexx unit options to exact addresses in LeFrak's
official building directory, preserves raw option HTML, stable `data-unit-id`
values, source URLs, retrieval time, and DOB NOW crosswalk evidence. It does not
expand LeFrak's building count, floorplans, or option patterns into a roster.
The lane is current-vacancy evidence, not complete portfolio coverage.

Relevant source documentation is in
[`docs/missing-units-roadmap.md`](docs/missing-units-roadmap.md),
[`docs/manager-feed-map.md`](docs/manager-feed-map.md), and
[`FEEDS.md`](FEEDS.md). The parser test is in
[`tests/test_spherexx.py`](tests/test_spherexx.py).

## Local reconciliation that was started after the last commit

An audit found that the ignored `listings.db` did not yet contain rows from several
already-shipped adapters. A bounded refresh was run to reconcile those existing
lanes; it was not a new source-discovery pass and should not be counted as citywide
coverage progress.

The resulting active listing database reported **6,671** rows. The refreshed adapter
results were:

| Adapter | Current rows | Interpretation |
|---|---:|---|
| Brodsky | 6 | Existing/current feed rows |
| C+C | 1 | Existing/current feed row |
| Dermot | 89 | Existing/current feed rows |
| Greystar | 8 | Existing/current feed rows |
| Lisa Management | 20 | Existing/current feed rows |
| Manhattan Skyline | 27 | Existing/current feed rows |
| Olnick | 11 | Existing/current feed rows |
| Rockrose | 46 | Existing/current feed rows |
| UDR | 23 | 23 new rows in the local listings snapshot |

Most of these were updates or rows already present. Only UDR produced a meaningful
new listing count in that pass. A listings refresh is not itself a canonical-unit
claim; catalog resolution still has to validate exact address, explicit unit label,
and BBL evidence.

The command below was run against
`/Users/mini-home/pricefixed-build/catalog.db` and completed, reporting:

```text
listings                       9328
observations                   21343
units                          3891
resolved_unit_observations     9716
unresolved_unit_observations   11627
```

The expensive final catalog status query was interrupted before the post-import
canonical total was re-read. On resume, measure that value first; do not infer a
canonical delta from the listing-row count.

## Next productive work

1. Verify the local build state before any new pull:

   ```bash
   cd /Users/mini-home/Desktop/unwalled
   git status --short
   python3 catalog.py --status --db /Users/mini-home/pricefixed-build/catalog.db
   ```

2. Do not replay the already-shipped manager adapters as a substitute for source
   acquisition. Their current-vacancy yield is small and their portfolios are not
   complete rosters.

3. Continue with the ranked primary-document queues:

   - Stuyvesant Town / Peter Cooper Village: 358 footprint addresses, 130 with
     direct unit evidence, 228 still needing a unit-bearing document or equivalent
     address-specific primary source. Use the existing outputs in `/tmp` and
     [`docs/complex-source-audit.md`](docs/complex-source-audit.md).
   - Targeted DOB occupancy documents: Certificates of Occupancy, Schedules of
     Occupancy, I-cards, filed plans, and other documents that actually contain
     unit labels. Counts alone are insufficient.
   - Targeted ACRIS legal-unit backlog, using the ranked queue and preserving raw
     document references. The `FT_` namespace replay is already complete; do not
     repeat it blindly.
   - DOF Statement-of-Account and unit-address bridges only where they resolve an
     already identified unit identity; an address or BBL alone is not enough.

4. The voter-file lane was checked and intentionally deferred. Do not request voter
   data unless the project owner explicitly reopens that decision. The Rose lane is
   also not an authorized next source in this handoff.

5. For every new lane: deterministic extraction first, raw evidence plus source URL
   and retrieval time, exact address, explicit unit label, separate BBL evidence,
   visible ambiguous/rejected candidates, focused tests, documentation, then an
   explicit-path commit. Never use `git add -A`.

## Resume checks

```bash
cd /Users/mini-home/Desktop/unwalled
env PYTHONPATH=. pytest -q
python3 catalog.py --status --db /Users/mini-home/pricefixed-build/catalog.db
```

The LeFrak lane was last verified with the full repository suite at **219 passed,
19 subtests passed**. Re-run the suite after any change. Keep the ignored local
databases separate from committed source evidence and never touch `soannoying/`.
