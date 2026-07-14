"""
Aggregated admin API router.

Every admin route lives in a domain sub-module (users, variant_mappings,
discoveries, annotation_sources, jobs, etl, category_rules), each exposing a
prefix-less APIRouter. They are folded here into one router that carries the
"/api/admin" prefix and applies the require_admin guard once, so no sub-router
can silently ship without it (enforced by test_admin_route_authz.py).
"""
from fastapi import APIRouter, Depends

from .schemas import require_admin
from .users import router as _users_router
from .variant_mappings import router as _variant_mappings_router
from .discoveries import router as _discoveries_router
from .annotation_sources import router as _annotation_sources_router
# Re-exported so backend/worker.py can import the shared AlphaMissense coord
# helper without reaching into a specific sub-module path.
from .annotation_sources import _extract_am_coords  # noqa: F401
from .jobs import router as _jobs_router
from .etl import router as _etl_router
from .category_rules import router as _category_rules_router

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

for _sub_router in (
    _users_router,
    _variant_mappings_router,
    _discoveries_router,
    _annotation_sources_router,
    _jobs_router,
    _etl_router,
    _category_rules_router,
):
    router.include_router(_sub_router)
