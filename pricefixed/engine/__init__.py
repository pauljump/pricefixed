"""pricefixed.engine — where the two halves of the data meet.

The `adapters/` side scrapes live *listings* (asking rents, unit-level, ephemeral).
The `record/` side builds the public *record* (one row per building, keyed by BBL).
They share no key: a listing knows a street address; a building knows its BBL.

This package is the join. `crosswalk` normalizes a street address the same way on
both sides so a live listing can attach to its building's public record — the move
the walled gardens make impossible.
"""
from .crosswalk import normalize_address, build_crosswalk, bbl_for_address

__all__ = ["normalize_address", "build_crosswalk", "bbl_for_address"]
