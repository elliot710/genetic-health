"""Re-export shim: variant_routes.py was split into the variant/ package.

Kept so `from backend.api.variant_routes import router` (main.py + tests),
direct helper imports, and any remaining `patch("backend.api.variant_routes.X")`
targets keep resolving. Behaviour-critical patches were repointed to the
variant.lookup / variant.search submodules where the handlers resolve them.
"""

from backend.api.variant import (  # noqa: F401
    router,
    VariantLookupRequest,
    VariantLookupResponse,
    validate_variant_id,
    _build_variant_lookup_description,
    get_variant_category,
    _create_multi_source_mappings,
    _generate_external_links,
)
# Patched-name re-exports so un-repointed patch targets still resolve (harmless).
from sqlalchemy import select, func as sa_func, literal_column  # noqa: F401
from backend.services.genetic_api_service import GeneticAPIService  # noqa: F401
from backend.services.discovery_service import process_lookup_discoveries  # noqa: F401
from backend.services.clinvar_local import get_clinvar_local_service  # noqa: F401
from backend.services.gnomad_local import get_gnomad_service  # noqa: F401
from backend.services.ensembl_vep_local import get_ensembl_local_service  # noqa: F401
from backend.utils.alpha_missense import get_alpha_missense_service  # noqa: F401
