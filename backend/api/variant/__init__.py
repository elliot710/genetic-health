"""Variant API package (split from the former variant_routes.py module).

Aggregates the lookup and search sub-routers into a single `router` mounted at
the same /api/variants prefix, and re-exports the helper functions.
"""

from fastapi import APIRouter

from .lookup import router as _lookup_router
from .search import router as _search_router
from .helpers import (
    VariantLookupRequest,
    VariantLookupResponse,
    validate_variant_id,
    _build_variant_lookup_description,
    get_variant_category,
    _create_multi_source_mappings,
    _generate_external_links,
)

router = APIRouter()
router.include_router(_lookup_router)
router.include_router(_search_router)
