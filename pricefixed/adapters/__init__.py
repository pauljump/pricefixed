"""Adapter registry. Add a source: drop a `SourceAdapter` subclass in this folder and
register it here. Keep the map alphabetical."""
from .avalonbay import AvalonBayAdapter
from .durst import DurstAdapter
from .glenwood import GlenwoodAdapter
from .nooklyn import NooklynAdapter
from .ogdencap import OgdenCapAdapter
from .securecafe import SecureCafeAdapter
from .stonehenge import StonehengeAdapter
from .stuytown import StuyTownAdapter
from .tfcornerstone import TFCornerstoneAdapter

ADAPTERS = {
    a.name: a
    for a in (
        AvalonBayAdapter,
        DurstAdapter,
        GlenwoodAdapter,
        NooklynAdapter,
        OgdenCapAdapter,
        SecureCafeAdapter,
        StonehengeAdapter,
        StuyTownAdapter,
        TFCornerstoneAdapter,
    )
}
