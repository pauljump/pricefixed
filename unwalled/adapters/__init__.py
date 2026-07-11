"""Adapter registry. Add a source: drop a `SourceAdapter` subclass in this folder and
register it here. Keep the map alphabetical."""
from .nooklyn import NooklynAdapter
from .stuytown import StuyTownAdapter
from .tfcornerstone import TFCornerstoneAdapter

ADAPTERS = {
    a.name: a
    for a in (StuyTownAdapter, TFCornerstoneAdapter, NooklynAdapter)
}
