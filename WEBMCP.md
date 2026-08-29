# Apartment Autopsy

Apartment Autopsy is the WebMCP-facing experiment built on pricefixed. It is not another
apartment marketplace and it does not book a tour. It gives a person and their agent a shared
evidence workspace for the moment before money, time, or personal information gets committed.

## The pitch

**Ask the agent to find a rental. Then ask it what the listing does not prove.**

The app combines a source-backed listing snapshot with the asking-price history that ordinary
marketplaces discard. It returns an evidence ledger, explicit unknowns, and a human-review packet
of questions to take to a landlord or broker.

That is the WebMCP angle: the agent is not guessing its way through filters or scraping a card.
It can call typed tools to search, inspect, compare, and draft a bounded next step while the
person sees the underlying evidence and decides what to do.

## Tools exposed at `/autopsy.html`

- `search_rentals`: filter the hosted source-backed fixture by rent, bedrooms, and borough.
- `inspect_listing`: return the current ask, captured price history, provenance, and explicit gaps.
- `compare_listings`: compare finalists by asking price, size, price-per-square-foot, and movement.
- `draft_due_diligence_packet`: create a visible, unsent question packet for human review.

The write tool does not contact a landlord, apply, reserve a unit, or spend money. It only changes
the page state and says so in its result.

## Honest prototype boundary

The hosted page contains a small export of real rows from the local `listings.db` snapshot dated
2026-08-03. It is deliberately labeled as a fixture. It does not claim that every listing is
available, and it does not manufacture a building-record join, concessions, fees, utilities,
maintenance history, or housing-quality conclusion when the fixture does not contain one.

The next contest slice is to publish a versioned, small public evidence bundle and add the
verified building-record joins from the full local catalog. The tool contract should stay the
same; the data source can grow underneath it.

## Local check

```bash
cd site
PORT=6811 node server.js
# open http://127.0.0.1:6811/autopsy.html in a WebMCP-capable browser
```

The page also works as an ordinary webpage when WebMCP is unavailable; it falls back to the
human-facing filters and inspection view.
