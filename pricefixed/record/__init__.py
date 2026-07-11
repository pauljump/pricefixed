"""Record-source registry. Add a source: drop a `RecordSource` subclass in this folder
and register it here. Keep the map alphabetical."""
from .core import RecordSource, add_events, init_record_db, socrata, upsert_building
from .dob_permits import DobPermitsSource
from .hpd_registrations import HpdRegistrationsSource
from .pluto import PlutoSource

RECORD_SOURCES = {
    s.name: s
    for s in (
        DobPermitsSource,
        HpdRegistrationsSource,
        PlutoSource,
    )
}

__all__ = [
    "RecordSource", "socrata", "init_record_db", "upsert_building", "add_events",
    "RECORD_SOURCES",
]
