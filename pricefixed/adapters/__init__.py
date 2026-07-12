"""Adapter registry. Add a source: drop a `SourceAdapter` subclass in this folder and
register it here. Keep the map alphabetical."""
from .appfolio import AppFolioAdapter
from .avalonbay import AvalonBayAdapter
from .corcoran import CorcoranSource
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
        AppFolioAdapter,
        AvalonBayAdapter,
        CorcoranSource,
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
