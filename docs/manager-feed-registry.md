# Manager Feed Registry

The machine-readable registry is `data/manager_feed_registry.jsonl`. It is
generated from the public NYBits manager directory and profile pages:

```bash
python3 tools/manager_feed_discovery.py \
  --output data/manager_feed_registry.jsonl
```

To make one bounded public homepage check for vendor fingerprints:

```bash
python3 tools/manager_feed_discovery.py \
  --output data/manager_feed_registry.jsonl \
  --probe-websites
```

To follow explicit property and leasing links exposed by those homepages:

```bash
python3 tools/manager_feed_discovery.py \
  --output data/manager_feed_registry.jsonl \
  --probe-websites \
  --discover-pages \
  --max-pages 8
```

To create a flat, reviewable path queue from the nested manager registry:

```bash
python3 tools/build_leasing_path_registry.py \
  --input data/manager_feed_registry.jsonl \
  --output data/public_leasing_paths.jsonl
```

To build the manager-level private-feed investigation queue:

```bash
python3 tools/build_feed_provenance_queue.py \
  --managers data/manager_feed_registry.jsonl \
  --paths data/public_leasing_paths.jsonl \
  --output data/feed_provenance_queue.jsonl
```

Use `--limit N` while developing. The runner is intentionally sequential and
rate-limited. Page discovery follows only links whose visible text or URL
clearly indicates a property, rental, availability, or leasing page, plus
explicit links to known vendor domains. It does not probe guessed feed
endpoints or access account-only areas.

## Row Contract

Each JSONL row records:

- manager identity and NYBits profile URL;
- building, managed-rental, and brokered-rental counts when displayed;
- the visible official website and candidate URLs;
- vendor hints found in the profile or optional homepage check;
- explicit public property/leasing pages found by the optional bounded crawl,
  including the source page and anchor text;
- `feed_status` and `transport_confidence`, which remain `unknown` until a
  public feed or a documented private transport is verified;
- evidence URLs, status, errors, and check time.

This registry is a discovery queue, not a unit catalog. A manager with a public
availability page may still have private weekly files or custom imports that
cannot be observed from the public site.

## Initial Snapshot

The first run on 2026-08-08 produced 31 manager rows:

- 27 managers had a visible official website on their NYBits profile.
- 20 of those homepages returned a public page to the bounded check.
- 7 website links failed or were stale and remain useful follow-up targets.
- Public vendor hints surfaced for Algin Management (AppFolio), Dermot Realty
  Management (SecureCafe), and Windsor Communities (SecureCafe and
  Funnel/Nestio-style links).

These are hints from public pages, not claims about the private transport NYBits
receives. The registry keeps those facts separate so each hint can become a
confirmed provider record after a focused follow-up.

The flat path file uses `evidence_level` values such as `public_page`,
`public_page_vendor_hint`, `public_vendor_portal`, and
`public_link_unchecked`. None of these labels claim that NYBits receives the
same data or uses the same transport.

## Linked-Page Snapshot

The expanded bounded crawl on 2026-08-08 checked 193 explicit property, leasing,
availability, or vendor links exposed by the official sites:

- 182 linked pages returned a public HTTP response.
- 16 of the 31 managers produced at least one usable linked-page result.
- Vendor fingerprints appeared in linked evidence for SecureCafe, AppFolio,
  MRI ProspectConnect, Funnel/Nestio, and RealPage/On-Site.

This is evidence about public site paths. It is not yet a claim that every
manager uses one of those vendors, or that NYBits receives the same data by the
same transport.

The provenance queue makes that uncertainty explicit. It prioritizes large
managers with no public path, vendor-linked managers whose NYBits transport is
still unknown, and managers with failed public paths. Its hypotheses are
research targets, not findings.
