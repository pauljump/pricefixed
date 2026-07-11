"""unwalled — open scraping tools for apartment listings. Point your AI agent at these
and build whatever inventory you want."""
from .core import SourceAdapter, fetch, init_db, upsert_listings
from .adapters import ADAPTERS

__version__ = "0.1.0"
__all__ = ["SourceAdapter", "fetch", "init_db", "upsert_listings", "ADAPTERS"]
