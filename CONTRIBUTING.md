# Contributing to Pricefixed

Pricefixed is building an open, evidence-backed registry of NYC housing and the
public asking-rent history attached to it. Contributions are welcome from developers,
researchers, journalists, tenants, and housing organizers.

The project accepts evidence and reproducible methods, not unsupported assertions.
Do not add a home merely because it seems likely to exist: retain the source, state
the rule, and preserve ambiguity when the evidence does not support one answer.

## Choose a contribution lane

### Add or repair a listing source

Add a public, landlord-direct availability source or repair one that has changed.
See [`COMPILE.md`](COMPILE.md) for the adapter workflow and
[`FEEDS.md`](FEEDS.md) for the source map. Open a [broken-feed issue](../../issues/new?template=broken-feed.md)
when a current source stops working.

### Add a public-record source

Add a source that contributes building, premise, unit, or event evidence. A source
must document its publisher, public access path, retrieval method, license or terms,
and the fields it contributes. Start with the
[registry-source issue template](../../issues/new?template=registry-source.md) before
writing a large importer so the scope can be reviewed early.

### Propose an identity rule

An identity rule is a deterministic transformation from source evidence to a building,
premise, unit, or unresolved-capacity claim. It must say what it proves, what it does
not prove, and include positive and negative fixtures. Use the
[resolution-rule template](../../issues/new?template=resolution-rule.md).

### Report a data-quality issue

Report a false match, missing source, questionable inference, or coverage gap with
the source record or a reproducible query. Do not post tenant names, account data, or
material obtained behind a login. Use the
[data-quality template](../../issues/new?template=data-quality.md).

### Improve documentation, tests, or release tooling

Small improvements matter: schema documentation, test fixtures, source freshness
checks, release manifests, and independent audits are all first-class contributions.

## Rules that protect the registry

- **Evidence first.** Every public record must retain source identity and retrieval
  context. A manual correction needs a public source reference.
- **Never fill gaps with invented homes.** A source-reported dwelling count can create
  unresolved capacity, not an apartment identity.
- **Keep the layers separate.** Source material, observations, entity matches, and
  registry records are distinct claims. See [`CATALOG.md`](CATALOG.md).
- **Make rules deterministic.** A reviewer must be able to rerun a rule on a fixture
  and get the same result.
- **Test the failure case.** Every matching rule needs at least one example it must
  refuse to resolve.
- **Use public, permitted sources.** Do not add data that requires a login, defeats an
  access control, or includes personal information that is not necessary for the
  housing record.
- **Do not add runtime dependencies casually.** Pricefixed currently runs on Python's
  standard library. Discuss a dependency before adding one.

## Add a listing adapter

An adapter is intentionally small. The framework handles HTTP, retries, SQLite,
price-history snapshots, and inactive listings; an adapter returns normalized listing
dicts.

1. Create `pricefixed/adapters/yourlandlord.py` by running
   `python3 new_adapter.py yourlandlord`.
2. Implement `pull()` and retain the source row in `raw_json`.
3. Register the adapter in `pricefixed/adapters/__init__.py`.
4. Run `python3 scrape.py --source yourlandlord --db /tmp/pricefixed-test.db`.
5. Add a focused test or fixture when parsing is nontrivial.
6. Open a focused pull request.

## Pull request checklist

State which contribution lane the PR belongs to. Include the source URL or public
dataset identifier, the affected entity layer, the expected quality effect, and the
commands you ran. Keep a change small enough that an outside reviewer can audit it.

For the data model and release interface, read [`REGISTRY.md`](REGISTRY.md) and
[`DATA.md`](DATA.md). For listing sources, read [`COMPILE.md`](COMPILE.md).
