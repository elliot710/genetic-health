"""Scoring engine package (split from the former scoring_engine.py module).

Re-exports the public surface so existing imports keep resolving.
"""

from .models import SourceEvidence, ScoringResult, _SOURCE_WEIGHTS
from .engine import ScoringEngine, get_scoring_engine

__all__ = [
    "SourceEvidence",
    "ScoringResult",
    "ScoringEngine",
    "get_scoring_engine",
    "_SOURCE_WEIGHTS",
]
