"""Database models package (split from the former db/models.py module).

Re-exports Base and every model so existing `from backend.db.models import X`
imports and Alembic's `from backend.db.models import *` keep resolving.
"""

from backend.db.database import Base

from .user import User, Notification, DashboardShare, SavedVariant
from .analysis import (
    GeneticAnalysis, GeneticMarker, AnalysisVariant, HealthRisk, DrugResponse,
)
from .dashboard_traits import (
    PhysicalTrait, NutritionTrait, SportsPerformance, CognitiveProfile,
    PersonalityTrait, AncestryResult, CarrierStatus, WellnessMetric,
    MethylationProfile, DetoxificationProfile,
)
from .annotations import (
    SharedVariantAnnotation, VariantAnnotation, RareMutation, UncommonMutation,
    VariantMapping, VariantLookupCache, AnnotationSourceConfig, PendingDiscovery,
)
from .reference_data import (
    ClinVarVariant, ClinVarGeneCondition, ClinVarGeneStats, CategoryRule,
    GnomadVariant, GnomadGeneConstraint, EnsemblGene, EnsemblVepVariant,
    ThousandGenomesVariant, GnomadV2Variant, DashboardCache, WorkerJob,
    AiInsightCache, GwasCatalogAssociation, ClinGenGeneValidity, OpenTargetsCache,
)

__all__ = [
    "Base",
    "User",
    "Notification",
    "DashboardShare",
    "SavedVariant",
    "GeneticAnalysis",
    "GeneticMarker",
    "AnalysisVariant",
    "HealthRisk",
    "DrugResponse",
    "PhysicalTrait",
    "NutritionTrait",
    "SportsPerformance",
    "CognitiveProfile",
    "PersonalityTrait",
    "AncestryResult",
    "CarrierStatus",
    "WellnessMetric",
    "MethylationProfile",
    "DetoxificationProfile",
    "SharedVariantAnnotation",
    "VariantAnnotation",
    "RareMutation",
    "UncommonMutation",
    "VariantMapping",
    "VariantLookupCache",
    "AnnotationSourceConfig",
    "PendingDiscovery",
    "ClinVarVariant",
    "ClinVarGeneCondition",
    "ClinVarGeneStats",
    "CategoryRule",
    "GnomadVariant",
    "GnomadGeneConstraint",
    "EnsemblGene",
    "EnsemblVepVariant",
    "ThousandGenomesVariant",
    "GnomadV2Variant",
    "DashboardCache",
    "WorkerJob",
    "AiInsightCache",
    "GwasCatalogAssociation",
    "ClinGenGeneValidity",
    "OpenTargetsCache",
]
