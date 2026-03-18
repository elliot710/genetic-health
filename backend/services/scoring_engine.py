"""
Unified Scoring & Confidence Engine — aggregates evidence from all annotation
sources into a single composite pathogenicity score (0–1) with confidence.

Sources integrated:
  - ClinVar clinical significance (local + API)
  - CADD PHRED score (gnomAD local)
  - AlphaMissense pathogenicity (local)
  - gnomAD allele frequency (local + BigQuery)
  - SIFT / PolyPhen predictions (gnomAD local)
  - PhyloP conservation (gnomAD local)
  - SpliceAI splice impact (gnomAD local)

The composite score feeds into dashboard risk assessments and
the VariantDetailDialog pathogenicity summary.

Usage:
    engine = ScoringEngine()
    result = engine.score_variant(annotation_data)
    # result = {
    #   "composite_score": 0.72,
    #   "confidence": "high",
    #   "evidence_count": 5,
    #   "classification": "likely_pathogenic",
    #   "sources": { ... per-source details ... },
    #   "conflicts": [ ... any contradictions ... ],
    # }
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source weights  — total should be ≈ 1.0 for normalization
# Higher weight = more trusted source for pathogenicity assessment
# ---------------------------------------------------------------------------
_SOURCE_WEIGHTS = {
    "clinvar":         0.30,   # Gold standard clinical curation
    "clinvar_local":   0.30,   # Same authority, local copy
    "cadd":            0.15,   # Computational deleteriousness
    "alpha_missense":  0.15,   # Deep learning missense prediction
    "gnomad_af":       0.10,   # Population frequency (rarity = more likely pathogenic)
    "sift":            0.05,   # Functional prediction
    "polyphen":        0.05,   # Functional prediction
    "conservation":    0.05,   # Evolutionary conservation
    "splice_ai":       0.05,   # Splice site impact
}


@dataclass
class SourceEvidence:
    """Evidence from a single annotation source."""
    source: str
    score: float           # 0.0 (benign) .. 1.0 (pathogenic)
    weight: float          # Source weight (from _SOURCE_WEIGHTS)
    label: str             # Human-readable interpretation
    raw_value: Any = None  # Original value for transparency


@dataclass
class ScoringResult:
    """Complete scoring result for a variant."""
    composite_score: float = 0.0
    confidence: str = "none"          # none, low, moderate, high
    evidence_count: int = 0
    classification: str = "uncertain" # benign, likely_benign, uncertain, likely_pathogenic, pathogenic
    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)
    total_weight: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composite_score": round(self.composite_score, 4),
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "classification": self.classification,
            "sources": self.sources,
            "conflicts": self.conflicts,
            "total_weight": round(self.total_weight, 3),
        }


class ScoringEngine:
    """Aggregates all evidence sources into a composite pathogenicity score."""

    # ACMG-like classification thresholds on the 0–1 scale
    PATHOGENIC_THRESHOLD = 0.80
    LIKELY_PATHOGENIC_THRESHOLD = 0.60
    UNCERTAIN_LOWER = 0.30
    BENIGN_THRESHOLD = 0.15

    # Minimum total weight for the composite score to be meaningful.
    # When only one source is available (e.g. ClinVar alone = 0.30),
    # dividing by a small denominator inflates the composite.
    # We clamp the denominator to at least this value.
    MIN_WEIGHT_FLOOR = 0.40

    def score_variant(self, annotations: Dict[str, Any]) -> Dict[str, Any]:
        """Score a variant using all available annotation sources.

        Args:
            annotations: Dict with source keys → source data, matching the
                         merged annotation format from analysis_service.py
                         (i.e. annotation_data['annotations']).

        Returns:
            ScoringResult as dict.
        """
        evidences: List[SourceEvidence] = []

        # 1. ClinVar (API)
        ev = self._score_clinvar(annotations.get("clinvar"))
        if ev:
            evidences.append(ev)

        # 2. ClinVar Local (PG)
        ev = self._score_clinvar_local(annotations.get("clinvar_local"))
        if ev:
            evidences.append(ev)

        # 3. gnomAD data (CADD, predictions, conservation, splice, AF)
        gnomad = annotations.get("gnomad")
        if gnomad and gnomad.get("found"):
            for ev in self._score_gnomad(gnomad):
                evidences.append(ev)

        # 4. AlphaMissense
        ev = self._score_alpha_missense(annotations.get("alpha_missense"))
        if ev:
            evidences.append(ev)

        # 5. Ensembl (VEP consequence impact)
        ev = self._score_ensembl(annotations.get("ensembl"))
        if ev:
            evidences.append(ev)

        return self._aggregate(evidences).to_dict()

    # ------------------------------------------------------------------
    # Per-source scorers
    # ------------------------------------------------------------------

    def _score_clinvar(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score ClinVar API data."""
        if not data or not data.get("found"):
            return None

        sig = self._extract_clinvar_significance(data)
        if not sig:
            return None

        score, label = self._clinvar_significance_to_score(sig)
        return SourceEvidence(
            source="clinvar", score=score,
            weight=_SOURCE_WEIGHTS["clinvar"], label=label, raw_value=sig,
        )

    def _score_clinvar_local(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score ClinVar local (PG) data."""
        if not data or not data.get("found"):
            return None

        sig = self._extract_clinvar_significance(data)
        if not sig:
            return None

        score, label = self._clinvar_significance_to_score(sig)
        return SourceEvidence(
            source="clinvar_local", score=score,
            weight=_SOURCE_WEIGHTS["clinvar_local"], label=label, raw_value=sig,
        )

    def _score_gnomad(self, data: Dict) -> List[SourceEvidence]:
        """Extract multiple evidence dimensions from gnomAD data."""
        results: List[SourceEvidence] = []

        # CADD PHRED
        cadd = data.get("cadd", {})
        phred = cadd.get("phred") if isinstance(cadd, dict) else None
        if phred is not None:
            score = self._cadd_to_score(phred)
            results.append(SourceEvidence(
                source="cadd", score=score,
                weight=_SOURCE_WEIGHTS["cadd"],
                label=cadd.get("interpretation", f"PHRED {phred}"),
                raw_value=phred,
            ))

        # SIFT
        preds = data.get("predictions", {})
        sift = preds.get("sift", {}) if isinstance(preds, dict) else {}
        if sift.get("score") is not None:
            # SIFT: low score = deleterious (inverted)
            sift_score = 1.0 - min(max(sift["score"], 0.0), 1.0)
            cat = sift.get("category", "")
            results.append(SourceEvidence(
                source="sift", score=sift_score,
                weight=_SOURCE_WEIGHTS["sift"],
                label=f"SIFT: {cat}" if cat else f"SIFT: {sift['score']:.3f}",
                raw_value=sift["score"],
            ))

        # PolyPhen
        polyphen = preds.get("polyphen", {}) if isinstance(preds, dict) else {}
        if polyphen.get("score") is not None:
            # PolyPhen: high score = damaging (same direction as ours)
            pp_score = min(max(polyphen["score"], 0.0), 1.0)
            cat = polyphen.get("category", "")
            results.append(SourceEvidence(
                source="polyphen", score=pp_score,
                weight=_SOURCE_WEIGHTS["polyphen"],
                label=f"PolyPhen: {cat}" if cat else f"PolyPhen: {polyphen['score']:.3f}",
                raw_value=polyphen["score"],
            ))

        # Conservation (PhyloP vertebrate)
        cons = data.get("conservation", {})
        vert = cons.get("vertebrate") if isinstance(cons, dict) else None
        if vert is not None:
            # PhyloP range: ~-20 to +10. High positive → conserved → more likely pathogenic.
            # Normalize: >=7 → 1.0, <=0 → 0.0
            cons_score = min(max(vert / 7.0, 0.0), 1.0)
            results.append(SourceEvidence(
                source="conservation", score=cons_score,
                weight=_SOURCE_WEIGHTS["conservation"],
                label=f"PhyloP vertebrate: {vert:.2f}",
                raw_value=vert,
            ))

        # SpliceAI
        splice = data.get("splice_ai", {})
        max_splice = splice.get("max_score") if isinstance(splice, dict) else None
        if max_splice is not None and max_splice > 0:
            # SpliceAI: 0–1, >0.5 = high splice impact
            results.append(SourceEvidence(
                source="splice_ai", score=min(max_splice, 1.0),
                weight=_SOURCE_WEIGHTS["splice_ai"],
                label=f"SpliceAI max: {max_splice:.3f}",
                raw_value=max_splice,
            ))

        # Allele frequency (rarity as pathogenicity evidence)
        af = data.get("af")
        if af is not None:
            af_score = self._af_to_score(af)
            results.append(SourceEvidence(
                source="gnomad_af", score=af_score,
                weight=_SOURCE_WEIGHTS["gnomad_af"],
                label=self._af_label(af),
                raw_value=af,
            ))

        return results

    def _score_alpha_missense(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score AlphaMissense prediction."""
        if not data:
            return None

        am_score = data.get("am_pathogenicity") or data.get("score") or data.get("pathogenicity_score")
        if am_score is None:
            return None

        try:
            am_score = float(am_score)
        except (ValueError, TypeError):
            return None

        # AlphaMissense score is already 0–1 (higher = more pathogenic)
        classification = data.get("am_class") or data.get("classification", "")
        return SourceEvidence(
            source="alpha_missense", score=am_score,
            weight=_SOURCE_WEIGHTS["alpha_missense"],
            label=f"AlphaMissense: {classification}" if classification else f"AM: {am_score:.3f}",
            raw_value=am_score,
        )

    def _score_ensembl(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score based on VEP consequence impact from Ensembl."""
        if not data or not data.get("found"):
            return None

        entries = data.get("data", [])
        if not entries:
            return None

        entry = entries[0] if isinstance(entries, list) else entries
        consequences = entry.get("most_severe_consequence", "")
        if not consequences:
            # Try transcript_consequences
            tc = entry.get("transcript_consequences", [])
            if tc:
                consequences = tc[0].get("consequence_terms", [""])[0] if isinstance(tc[0].get("consequence_terms"), list) else ""

        if not consequences:
            return None

        score = self._consequence_to_score(consequences)
        if score is None:
            return None

        return SourceEvidence(
            source="ensembl_vep", score=score,
            weight=0.05,  # VEP consequence alone is weak evidence
            label=f"VEP: {consequences}",
            raw_value=consequences,
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(self, evidences: List[SourceEvidence]) -> ScoringResult:
        """Weighted average of all evidence sources with conflict detection."""
        result = ScoringResult()

        if not evidences:
            return result

        # Deduplicate: if both clinvar + clinvar_local present, keep higher-weight
        # (they represent the same authority, so we take the one with more data)
        has_clinvar_api = any(e.source == "clinvar" for e in evidences)
        has_clinvar_local = any(e.source == "clinvar_local" for e in evidences)
        if has_clinvar_api and has_clinvar_local:
            # Prefer API ClinVar (more structured), drop local
            evidences = [e for e in evidences if e.source != "clinvar_local"]

        # BUG-12: ClinVar authoritative override.
        # When ClinVar asserts Pathogenic (score >= 0.80) and no other source
        # calls the variant clearly Benign, preserve the ClinVar classification
        # rather than diluting it through MIN_WEIGHT_FLOOR.
        # (ACMG 2015: a ClinVar Pathogenic assertion is PVS1-level evidence.)
        clinvar_evs = [e for e in evidences if e.source in ("clinvar", "clinvar_local")]
        if clinvar_evs:
            best_cv = max(clinvar_evs, key=lambda e: e.score)
            has_benign_conflict = any(
                e.score < 0.30
                for e in evidences
                if e.source not in ("clinvar", "clinvar_local")
            )
            if best_cv.score > 0.80 and not has_benign_conflict:
                conflicts = self._detect_conflicts(evidences)
                total_w = sum(e.weight for e in evidences)
                result.composite_score = best_cv.score
                result.classification = self._classify(best_cv.score)
                result.evidence_count = len(evidences)
                result.total_weight = total_w
                result.sources = {
                    e.source: {
                        "score": round(e.score, 4),
                        "weight": e.weight,
                        "label": e.label,
                        "raw_value": e.raw_value,
                    }
                    for e in evidences
                }
                result.conflicts = conflicts
                result.confidence = self._compute_confidence(
                    len(evidences), total_w, len(conflicts) * 0.15
                )
                return result

        # Weighted average with minimum weight floor to prevent
        # single-source inflation (e.g. ClinVar-only = 0.30 weight
        # would otherwise make the composite equal to the raw score).
        total_weight = sum(e.weight for e in evidences)
        if total_weight == 0:
            return result

        weighted_sum = sum(e.score * e.weight for e in evidences)
        effective_weight = max(total_weight, self.MIN_WEIGHT_FLOOR)
        composite = weighted_sum / effective_weight

        # Detect conflicts
        conflicts = self._detect_conflicts(evidences)

        # If major conflict, reduce confidence
        confidence_penalty = 0.0
        if conflicts:
            confidence_penalty = len(conflicts) * 0.15

        # Build per-source details
        sources = {}
        for e in evidences:
            sources[e.source] = {
                "score": round(e.score, 4),
                "weight": e.weight,
                "label": e.label,
                "raw_value": e.raw_value,
            }

        result.composite_score = composite
        result.evidence_count = len(evidences)
        result.total_weight = total_weight
        result.sources = sources
        result.conflicts = conflicts
        result.confidence = self._compute_confidence(
            len(evidences), total_weight, confidence_penalty
        )
        result.classification = self._classify(composite)

        return result

    def _detect_conflicts(self, evidences: List[SourceEvidence]) -> List[str]:
        """Detect contradictions between evidence sources."""
        conflicts = []

        benign_sources = [e for e in evidences if e.score < 0.3]
        pathogenic_sources = [e for e in evidences if e.score > 0.7]

        if benign_sources and pathogenic_sources:
            b_names = ", ".join(e.source for e in benign_sources)
            p_names = ", ".join(e.source for e in pathogenic_sources)
            conflicts.append(
                f"Conflicting evidence: {p_names} suggest pathogenic "
                f"while {b_names} suggest benign"
            )

        # ClinVar vs computational
        clinvar_evs = [e for e in evidences if e.source in ("clinvar", "clinvar_local")]
        cadd_evs = [e for e in evidences if e.source == "cadd"]
        am_evs = [e for e in evidences if e.source == "alpha_missense"]

        for cv in clinvar_evs:
            for comp in cadd_evs + am_evs:
                if abs(cv.score - comp.score) > 0.5:
                    conflicts.append(
                        f"ClinVar ({cv.label}) disagrees with "
                        f"{comp.source} ({comp.label})"
                    )

        return conflicts

    def _compute_confidence(
        self, evidence_count: int, total_weight: float, penalty: float
    ) -> str:
        """Determine confidence level based on evidence quantity and quality."""
        # Base confidence from evidence count and total weight
        # More independent sources + higher total weight = higher confidence
        base = min(evidence_count / 4, 1.0) * 0.5 + min(total_weight / 0.6, 1.0) * 0.5
        confidence_score = max(base - penalty, 0.0)

        if confidence_score >= 0.7:
            return "high"
        elif confidence_score >= 0.4:
            return "moderate"
        elif confidence_score >= 0.15:
            return "low"
        return "none"

    def _classify(self, score: float) -> str:
        """Map composite score to ACMG-like classification."""
        if score >= self.PATHOGENIC_THRESHOLD:
            return "pathogenic"
        elif score >= self.LIKELY_PATHOGENIC_THRESHOLD:
            return "likely_pathogenic"
        elif score >= self.UNCERTAIN_LOWER:
            return "uncertain"
        elif score >= self.BENIGN_THRESHOLD:
            return "likely_benign"
        return "benign"

    # ------------------------------------------------------------------
    # Value converters
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_clinvar_significance(data: Dict) -> str:
        """Extract clinical significance string from various ClinVar data formats.
        Handles both API format (data[0].clinical_significance as string)
        and local format (entries[0].clinical_significance as list)."""
        # Direct string
        sig = data.get("clinical_significance", "")
        if isinstance(sig, list):
            sig = sig[0] if sig else ""
        if sig:
            return sig

        # Nested in data array (API format)
        if isinstance(data.get("data"), list) and data["data"]:
            s = data["data"][0].get("clinical_significance", "")
            if isinstance(s, list):
                s = s[0] if s else ""
            if s:
                return s
        elif isinstance(data.get("data"), dict):
            s = data["data"].get("clinical_significance", "")
            if isinstance(s, list):
                s = s[0] if s else ""
            if s:
                return s

        # Nested in entries array (local ClinVar format)
        entries = data.get("entries", [])
        if entries and isinstance(entries, list):
            s = entries[0].get("clinical_significance", "")
            if isinstance(s, list):
                s = s[0] if s else ""
            if s:
                return s

        return ""

    @staticmethod
    def _clinvar_significance_to_score(sig: str) -> Tuple[float, str]:
        """Convert ClinVar clinical significance string to a 0–1 score."""
        sig_lower = sig.lower().strip()

        # Handle compound significances like "Pathogenic/Likely_pathogenic"
        if "/" in sig_lower:
            parts = sig_lower.split("/")
            # Take the most severe
            scores = [ScoringEngine._clinvar_significance_to_score(p.strip()) for p in parts]
            return max(scores, key=lambda x: x[0])

        mapping = {
            "pathogenic":            (0.95, "Pathogenic"),
            "likely pathogenic":     (0.80, "Likely pathogenic"),
            "likely_pathogenic":     (0.80, "Likely pathogenic"),
            "uncertain significance":(0.50, "Uncertain significance"),
            "uncertain_significance":(0.50, "Uncertain significance"),
            "likely benign":         (0.20, "Likely benign"),
            "likely_benign":         (0.20, "Likely benign"),
            "benign":               (0.05, "Benign"),
            "risk factor":          (0.60, "Risk factor"),
            "risk_factor":          (0.60, "Risk factor"),
            "protective":           (0.05, "Protective"),
            "drug response":        (0.50, "Drug response"),
            "drug_response":        (0.50, "Drug response"),
            "association":          (0.55, "Association"),
            "affects":              (0.50, "Affects"),
            "conflicting interpretations": (0.50, "Conflicting interpretations"),
            "conflicting_interpretations_of_pathogenicity": (0.50, "Conflicting interpretations"),
        }

        for key, (score, label) in mapping.items():
            if key in sig_lower:
                return score, label

        return 0.50, f"Unknown: {sig}"

    @staticmethod
    def _cadd_to_score(phred: float) -> float:
        """Convert CADD PHRED to 0–1. PHRED ≥30 → ~1.0, ≤5 → ~0.1."""
        if phred >= 30:
            return 0.95
        elif phred >= 20:
            return 0.75 + (phred - 20) * 0.02  # 0.75–0.95
        elif phred >= 15:
            return 0.55 + (phred - 15) * 0.04  # 0.55–0.75
        elif phred >= 10:
            return 0.35 + (phred - 10) * 0.04  # 0.35–0.55
        elif phred >= 5:
            return 0.15 + (phred - 5) * 0.04   # 0.15–0.35
        return max(phred / 5.0 * 0.15, 0.0)

    @staticmethod
    def _af_to_score(af: float) -> float:
        """Convert allele frequency to pathogenicity score.
        Rare variants are more likely to be pathogenic.
        AF=0 is ambiguous (could be data-missing, not ultra-rare),
        so scored moderately rather than near-pathogenic.
        AF>5% → 0.1 (common, less likely pathogenic)
        """
        if af <= 0.0:
            return 0.50  # Not observed — ambiguous, don't inflate
        elif af < 0.0001:  # < 0.01%  (ultra-rare, confirmed present)
            return 0.85
        elif af < 0.001:   # < 0.1%
            return 0.70
        elif af < 0.01:    # < 1%
            return 0.50
        elif af < 0.05:    # < 5%
            return 0.25
        return 0.10

    @staticmethod
    def _af_label(af: float) -> str:
        if af <= 0:
            return "Not observed in gnomAD"
        elif af < 0.0001:
            return f"Ultra-rare (AF={af:.6f})"
        elif af < 0.001:
            return f"Very rare (AF={af:.5f})"
        elif af < 0.01:
            return f"Rare (AF={af:.4f})"
        elif af < 0.05:
            return f"Low frequency (AF={af:.3f})"
        return f"Common (AF={af:.3f})"

    @staticmethod
    def _consequence_to_score(consequence: str) -> Optional[float]:
        """Map VEP consequence to pathogenicity score."""
        c = consequence.lower().replace(" ", "_")
        high_impact = {
            "transcript_ablation", "splice_acceptor_variant", "splice_donor_variant",
            "stop_gained", "frameshift_variant", "stop_lost", "start_lost",
        }
        moderate_impact = {
            "inframe_insertion", "inframe_deletion", "missense_variant",
            "protein_altering_variant",
        }
        low_impact = {
            "splice_region_variant", "synonymous_variant",
            "start_retained_variant", "stop_retained_variant",
        }

        if c in high_impact:
            return 0.85
        elif c in moderate_impact:
            return 0.55
        elif c in low_impact:
            return 0.25
        elif "intron" in c or "downstream" in c or "upstream" in c or "intergenic" in c:
            return 0.10
        return None


# Module-level singleton
_instance: Optional[ScoringEngine] = None


def get_scoring_engine() -> ScoringEngine:
    global _instance
    if _instance is None:
        _instance = ScoringEngine()
    return _instance
