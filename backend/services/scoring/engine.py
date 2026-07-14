"""ScoringEngine: dispatch, aggregation, conflict detection and the module
singleton (split out of scoring_engine.py)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from backend.services.scoring.models import SourceEvidence, ScoringResult
from backend.services.scoring.source_scorers import _SourceScorers


class ScoringEngine(_SourceScorers):
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

        # 6. GWAS Catalog (genome-wide significant associations)
        ev = self._score_gwas_catalog(annotations.get("gwas_catalog"))
        if ev:
            evidences.append(ev)

        # 7. ClinGen gene validity (Definitive/Strong/Moderate/Limited)
        ev = self._score_clingen(annotations.get("clingen"))
        if ev:
            evidences.append(ev)

        # 8. Open Targets (genetic association score)
        ev = self._score_open_targets(annotations.get("open_targets"))
        if ev:
            evidences.append(ev)

        # 9. AlphaFold structural confidence
        ev = self._score_alphafold(annotations.get("alphafold"))
        if ev:
            evidences.append(ev)

        # 10. LitVar literature evidence
        ev = self._score_litvar(annotations.get("litvar"))
        if ev:
            evidences.append(ev)

        # 11. Gene constraint (pLI/LOEUF from gnomAD)
        ev = self._score_gene_constraint(annotations.get("gene_constraint"))
        if ev:
            evidences.append(ev)

        # 12. ClinVar gene-level burden (pathogenic ratio for the gene)
        ev = self._score_clinvar_gene_stats(annotations.get("clinvar_gene_stats"))
        if ev:
            evidences.append(ev)

        # 13. ChEMBL druggability (approved drugs targeting this gene)
        ev = self._score_chembl(annotations.get("chembl"))
        if ev:
            evidences.append(ev)

        # 14. FDA drug interactions / CYP involvement
        ev = self._score_fda_drug(annotations.get("fda_drug"))
        if ev:
            evidences.append(ev)

        # 15. gnomAD-tx LoF annotation + tissue expression
        ev = self._score_gnomad_tx(annotations.get("gnomad_tx"))
        if ev:
            evidences.append(ev)

        return self._aggregate(evidences).to_dict()

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(self, evidences: List[SourceEvidence]) -> ScoringResult:
        """Weighted average of all evidence sources with conflict detection."""
        result = ScoringResult()

        if not evidences:
            # No evidence → score stays 0.0, classify accordingly (benign)
            # rather than leaving the default "uncertain".
            result.classification = self._classify(result.composite_score)
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
