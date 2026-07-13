"""Enrichment-source registry. Add a source: drop an `EnrichmentSource` subclass in
this folder. It auto-registers — no central list to edit — so an agent cranking new
rows just writes the file.

Open to more on request: if the context you want isn't here, open an issue and it
becomes another row. See FEEDS.md (enrichment tier) for what's mapped.

Discovery is defensive: an import that fails (a half-built or drifted adapter) is
skipped with a warning rather than taking down the whole registry, the same way one
broken feed never kills a scrape run."""
import importlib
import pkgutil
import warnings

from .core import (
    EnrichmentSource, init_enrichment, ensure_columns, upsert_enrichment,
    buildings_with_points, buildings_with_areas, haversine, point_in_polygon,
    census_geoid,
)

ENRICHERS = {}
for _finder, _modname, _ispkg in pkgutil.iter_modules(__path__):
    if _modname == "core":
        continue
    try:
        _mod = importlib.import_module(f"{__name__}.{_modname}")
    except Exception as _e:  # noqa: BLE001 — a broken adapter is skipped, not fatal
        warnings.warn(f"enrichment: skipped {_modname} ({type(_e).__name__}: {_e})")
        continue
    for _obj in vars(_mod).values():
        if (isinstance(_obj, type) and issubclass(_obj, EnrichmentSource)
                and _obj is not EnrichmentSource and getattr(_obj, "name", "")):
            ENRICHERS[_obj.name] = _obj

__all__ = [
    "EnrichmentSource", "init_enrichment", "ensure_columns", "upsert_enrichment",
    "buildings_with_points", "buildings_with_areas", "haversine", "point_in_polygon",
    "census_geoid", "ENRICHERS",
]
