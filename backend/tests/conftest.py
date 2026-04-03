import sys
import os
from types import ModuleType
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class _AutoStubModule(ModuleType):
    """Returns a MagicMock for any attribute access — avoids listing every symbol."""

    _cache: dict = {}

    def __getattr__(self, name: str):
        if name.startswith('__'):
            raise AttributeError(name)
        if name not in self._cache:
            self._cache[name] = MagicMock()
        return self._cache[name]


class _ModelStubMeta(type):
    """Metaclass that returns a MagicMock for any class-level attribute access.

    This makes stub model classes support SQLAlchemy-style column expressions
    like ``GeneticAnalysis.id == 1`` and ``GeneticAnalysis.user_id.in_([1, 2])``
    without requiring actual SQLAlchemy mapping.
    """
    def __getattr__(cls, name: str):
        return MagicMock()


def _stub_init(self, *args, **kwargs):
    for k, v in kwargs.items():
        object.__setattr__(self, k, v)


def _stub_getattr(self, name):
    if name.startswith('__'):
        raise AttributeError(name)
    return MagicMock()


_models_stub = _AutoStubModule('backend.db.models')
_models_stub._cache = {}
# Provide proper stub *classes* (not MagicMocks) for type annotations
for _cls_name in ('AnalysisVariant', 'GeneticMarker', 'SharedVariantAnnotation',
                  'VariantAnnotation', 'GeneticAnalysis', 'DashboardCache',
                  'User', 'HealthRisk', 'DrugResponse', 'AncestryResult',
                  'SportsPerformance', 'NutritionTrait', 'CarrierStatus',
                  'MethylationProfile', 'DetoxificationProfile', 'RareMutation',
                  'WellnessMetric', 'PhysicalTrait', 'CognitiveProfile',
                  'PersonalityTrait', 'UncommonMutation', 'ClinVarGeneStats',
                  'ClinVarGeneCondition', 'SavedVariant', 'WorkerJob',
                  'PendingDiscovery', 'VariantMapping', 'Notification',
                  'AlphaMissense', 'GnomadV2Variant',
                  'CategoryRule', 'ClinVarVariant', 'ClinVarGeneCondition',
                  'GnomadVariant', 'GnomadGeneConstraint', 'EnsemblGene',
                  'AnnotationSourceConfig',
                  ):
    setattr(_models_stub, _cls_name, _ModelStubMeta(_cls_name, (), {
        '__init__': _stub_init,
        '__getattr__': _stub_getattr,
    }))
sys.modules['backend.db.models'] = _models_stub

_db_stub = _AutoStubModule('backend.db.database')
_db_stub._cache = {}
_db_stub.async_session_factory = MagicMock()
_db_stub.get_session = MagicMock()
sys.modules['backend.db.database'] = _db_stub

_settings_obj = MagicMock(
    database_url="postgresql+asyncpg://test:test@localhost/test",
    jwt_secret_key="test-secret",
    jwt_algorithm="HS256",
    ncbi_api_key=None,
)
_settings_stub = _AutoStubModule('backend.core.config')
_settings_stub._cache = {}
_settings_stub.settings = _settings_obj
sys.modules['backend.core.config'] = _settings_stub

_auth_stub = _AutoStubModule('backend.core.auth')
_auth_stub._cache = {}
sys.modules['backend.core.auth'] = _auth_stub


