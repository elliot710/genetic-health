"""Re-export shim: gnomad_local.py was split into the gnomad/ package.

Kept so existing `from backend.services.gnomad_local import X` imports and the
`_SQLITE_FILE` monkeypatch in tests continue to resolve against this module.
"""

from backend.services.gnomad import (  # noqa: F401
    GnomadCacheService,
    GnomadLocalService,
    GnomadTxService,
    get_gnomad_cache_service,
    get_gnomad_service,
    get_gnomad_tx_service,
    _GNOMAD_DATA_DIR,
    _CACHE_DIR,
    _SQLITE_FILE,
    _META_FILE,
)
