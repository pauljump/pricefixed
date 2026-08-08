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

Use `--limit N` while developing. The runner is intentionally sequential and
rate-limited. It reads public manager pages, does not follow discovered links,
and does not probe guessed feed endpoints.

## Row Contract

Each JSONL row records:

- manager identity and NYBits profile URL;
- building, managed-rental, and brokered-rental counts when displayed;
- the visible official website and candidate URLs;
- vendor hints found in the profile or optional homepage check;
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
