"""Record-source registry. Add a source: drop a `RecordSource` subclass in this folder
and register it here. Keep the map alphabetical."""
from .core import RecordSource, add_events, init_record_db, socrata, upsert_building
from .acris_sales import AcrisSalesSource
from .cofo import CofoSource
from .dob_complaints import DobComplaintsSource
from .dob_permits import DobPermitsSource
from .evictions import EvictionsSource
from .hpd_complaints import HpdComplaintsSource
from .hpd_registrations import HpdRegistrationsSource
from .litigation import HpdLitigationSource
from .pluto import PlutoSource
from .rent_stabilization import RentStabilizationSource
from .service_requests_311 import ServiceRequests311Source
from .violations import HpdViolationsSource

RECORD_SOURCES = {
    s.name: s
    for s in (
        AcrisSalesSource,
        CofoSource,
        DobComplaintsSource,
        DobPermitsSource,
        EvictionsSource,
        HpdComplaintsSource,
        HpdRegistrationsSource,
        HpdLitigationSource,
        PlutoSource,
        RentStabilizationSource,
        ServiceRequests311Source,
        HpdViolationsSource,
    )
}

__all__ = [
    "RecordSource", "socrata", "init_record_db", "upsert_building", "add_events",
    "RECORD_SOURCES",
]
