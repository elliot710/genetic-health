"""gnomAD service package (split from the former gnomad_local.py module).

Re-exports the full public surface so existing
`from backend.services.gnomad import X` imports keep resolving.
"""

from .cache import (
    GnomadCacheService,
    get_gnomad_cache_service,
    _GNOMAD_DATA_DIR,
    _CACHE_DIR,
    _SQLITE_FILE,
    _META_FILE,
)
from .service import GnomadLocalService, get_gnomad_service
from .tx import GnomadTxService, get_gnomad_tx_service

__all__ = [
    "GnomadCacheService",
    "get_gnomad_cache_service",
    "GnomadLocalService",
    "get_gnomad_service",
    "GnomadTxService",
    "get_gnomad_tx_service",
    "_GNOMAD_DATA_DIR",
    "_CACHE_DIR",
    "_SQLITE_FILE",
    "_META_FILE",
]
