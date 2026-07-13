"""Re-export shim: scoring_engine.py was split into the scoring/ package.

Kept so existing `from backend.services.scoring_engine import X` imports and the
`patch("backend.services.scoring_engine.get_scoring_engine", ...)` monkeypatches
keep resolving against this module.
"""

from backend.services.scoring import (  # noqa: F401
    SourceEvidence,
    ScoringResult,
    ScoringEngine,
    get_scoring_engine,
    _SOURCE_WEIGHTS,
)
