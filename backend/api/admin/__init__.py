"""
Aggregated admin API router.

`router` is resolved lazily via module __getattr__ (PEP 562) instead of
being imported eagerly: admin_routes.py imports from .admin.schemas, which
forces this package's __init__.py to run first. If this file eagerly
imported admin_routes.router in turn, whichever import started first would
capture the router before all of its @router.* handlers had registered --
the two modules import each other. Deferring the lookup to first attribute
access means it always resolves after both modules are fully loaded,
regardless of which one a caller imports first.

The require_admin guard is applied once, directly on admin_routes.router's
own construction (see its `dependencies=`), and is inherited by
admin.users's router when admin_routes.py folds it in via
router.include_router().
"""


def __getattr__(name):
    if name == "router":
        from ..admin_routes import router
        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
