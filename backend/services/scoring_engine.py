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
    "alphafold":       0.03,   # Structural confidence (low pLDDT = disordered)
    "litvar":          0.03,   # Literature evidence (well-studied variant)
    "gene_constraint":  0.05,  # Gene intolerance to LoF (pLI/LOEUF)
    "clinvar_gene_stats": 0.05, # Gene-level ClinVar pathogenic burden
    "chembl":          0.03,   # Druggability — known drug targets
    "fda_drug":        0.03,   # FDA drug interactions / CYP involvement
    "gnomad_tx":       0.05,   # LoF annotation + tissue expression
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

    def _score_gwas_catalog(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score based on GWAS Catalog genome-wide significant associations.

        A GWS hit (p≤5e-8) indicates the variant is reliably associated with a
        trait, but does NOT imply pathogenicity — it raises evidence weight only.
        """
        if not data or not data.get("found"):
            return None
        is_gws = data.get("genome_wide_significant", False)
        top_p = data.get("top_p_value")
        if not is_gws and (top_p is None or top_p > 5e-8):
            return None
        return SourceEvidence(
            source="gwas_catalog",
            score=0.45,
            weight=0.08,
            label=f"GWAS: {(data.get('top_trait') or 'trait association')[:60]}",
            raw_value=top_p,
        )

    def _score_clingen(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score based on ClinGen gene validity classification."""
        if not data or not data.get("found"):
            return None
        classification = data.get("strongest_classification") or ""
        score_map = {
            "Definitive": (0.75, 0.20),
            "Strong":     (0.65, 0.18),
            "Moderate":   (0.55, 0.12),
            "Limited":    (0.40, 0.06),
            "Animal Model Only": (0.35, 0.04),
            "Disputed":   (0.20, 0.05),
            "Refuted":    (0.05, 0.10),
            "No Known Disease Relationship": (0.02, 0.05),
        }
        entry = score_map.get(classification)
        if not entry:
            return None
        score, weight = entry
        return SourceEvidence(
            source="clingen",
            score=score,
            weight=weight,
            label=f"ClinGen: {classification}",
            raw_value=classification,
        )

    def _score_open_targets(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score based on Open Targets genetic association evidence."""
        if not data or not data.get("found"):
            return None
        max_score = data.get("max_score")
        if not max_score or max_score < 0.1:
            return None
        has_genetic = data.get("has_strong_genetic_evidence", False)
        weight = 0.15 if has_genetic else 0.08
        adjusted_score = min(0.70, max_score * 0.85)
        disease = data.get("top_disease") or "disease"
        return SourceEvidence(
            source="open_targets",
            score=adjusted_score,
            weight=weight,
            label=f"OT: {disease[:50]} ({max_score:.2f})",
            raw_value=max_score,
        )

    def _score_alphafold(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score based on AlphaFold structural confidence (pLDDT).

        Low global pLDDT indicates disordered/unstructured regions where
        missense variants are LESS likely to be damaging. High pLDDT means
        the region is well-structured and mutations more likely disruptive.
        """
        if not data or not data.get("found"):
            return None
        confidence = data.get("global_confidence")
        if confidence is None:
            return None
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            return None
        # pLDDT 0-100: >90 = very high confidence (structured),
        # 70-90 = confident, 50-70 = low, <50 = very low (disordered)
        if confidence >= 90:
            score = 0.60
        elif confidence >= 70:
            score = 0.45
        elif confidence >= 50:
            score = 0.30
        else:
            score = 0.15
        return SourceEvidence(
            source="alphafold", score=score,
            weight=_SOURCE_WEIGHTS["alphafold"],
            label=f"AlphaFold pLDDT: {confidence:.1f}",
            raw_value=confidence,
        )

    def _score_litvar(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score based on LitVar literature evidence.

        More publications = better-studied variant = higher evidence weight.
        This doesn't indicate pathogenicity direction — it increases confidence.
        """
        if not data or not data.get("found"):
            return None
        pub_count = data.get("total_publications", 0)
        if not pub_count or pub_count < 1:
            return None
        if pub_count >= 100:
            score = 0.55
        elif pub_count >= 20:
            score = 0.50
        elif pub_count >= 5:
            score = 0.45
        else:
            score = 0.40
        return SourceEvidence(
            source="litvar", score=score,
            weight=_SOURCE_WEIGHTS["litvar"],
            label=f"LitVar: {pub_count} publications",
            raw_value=pub_count,
        )

    def _score_gene_constraint(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score based on gnomAD gene constraint metrics.

        High pLI (>0.9) or low LOEUF (<0.35) indicates the gene is
        intolerant to loss-of-function variants — mutations in such genes
        are more likely to be pathogenic.
        """
        if not data:
            return None
        pli = data.get("pli")
        loeuf = data.get("loeuf")
        if pli is None and loeuf is None:
            return None
        score = 0.40
        label_parts = []
        if loeuf is not None:
            if loeuf < 0.35:
                score = 0.75
                label_parts.append(f"LOEUF={loeuf:.2f} (highly constrained)")
            elif loeuf < 0.6:
                score = 0.55
                label_parts.append(f"LOEUF={loeuf:.2f} (constrained)")
            else:
                score = 0.25
                label_parts.append(f"LOEUF={loeuf:.2f} (tolerant)")
        elif pli is not None:
            if pli > 0.9:
                score = 0.70
                label_parts.append(f"pLI={pli:.2f} (LoF intolerant)")
            elif pli > 0.5:
                score = 0.50
                label_parts.append(f"pLI={pli:.2f}")
            else:
                score = 0.25
                label_parts.append(f"pLI={pli:.2f} (LoF tolerant)")
        return SourceEvidence(
            source="gene_constraint", score=score,
            weight=_SOURCE_WEIGHTS["gene_constraint"],
            label="; ".join(label_parts) if label_parts else "Gene constraint",
            raw_value=data,
        )

    def _score_clinvar_gene_stats(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score gene-level ClinVar burden.

        High pathogenic/total ratio = gene has many known pathogenic variants,
        so new variants in this gene are more likely pathogenic.
        """
        if not data:
            return None
        total = data.get("total_submissions", 0)
        pathogenic = data.get("pathogenic_count", 0)
        if not total or total < 5:
            return None
        ratio = pathogenic / total
        if ratio >= 0.30:
            score = 0.70
        elif ratio >= 0.15:
            score = 0.55
        elif ratio >= 0.05:
            score = 0.40
        else:
            score = 0.20
        return SourceEvidence(
            source="clinvar_gene_stats", score=score,
            weight=_SOURCE_WEIGHTS["clinvar_gene_stats"],
            label=f"Gene ClinVar burden: {pathogenic}/{total} pathogenic ({ratio:.0%})",
            raw_value=data,
        )

    def _score_chembl(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score based on ChEMBL druggability.

        Genes targeted by approved drugs (max_phase=4) are pharmacogenomically
        important — variants may affect drug response.
        """
        if not data or not data.get("found"):
            return None
        drugs = data.get("drugs", [])
        if not drugs:
            return None
        approved = sum(1 for d in drugs if (d.get("max_phase") or 0) >= 4)
        warnings = len(data.get("warnings", []))
        if approved > 0 and warnings > 0:
            score = 0.65
        elif approved > 0:
            score = 0.55
        elif len(drugs) >= 5:
            score = 0.45
        else:
            score = 0.35
        return SourceEvidence(
            source="chembl", score=score,
            weight=_SOURCE_WEIGHTS["chembl"],
            label=f"ChEMBL: {len(drugs)} drugs ({approved} approved)",
            raw_value={"drug_count": len(drugs), "approved": approved},
        )

    def _score_fda_drug(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score based on FDA drug labels and CYP enzyme involvement.

        CYP enzyme mentions indicate pharmacogenomic relevance — variants
        in CYP genes or their targets may alter drug metabolism.
        """
        if not data or not data.get("found"):
            return None
        labels = data.get("labels", [])
        if not labels:
            return None
        cyp_genes: set = set()
        for lbl in labels:
            cyp_genes.update(lbl.get("cyp_enzymes", []))
        has_interactions = any(lbl.get("drug_interactions") for lbl in labels)
        if cyp_genes and has_interactions:
            score = 0.60
        elif cyp_genes:
            score = 0.50
        elif has_interactions:
            score = 0.45
        else:
            score = 0.35
        return SourceEvidence(
            source="fda_drug", score=score,
            weight=_SOURCE_WEIGHTS["fda_drug"],
            label=f"FDA: {len(labels)} labels, {len(cyp_genes)} CYP enzymes",
            raw_value={"label_count": len(labels), "cyp_count": len(cyp_genes)},
        )

    def _score_gnomad_tx(self, data: Optional[Dict]) -> Optional[SourceEvidence]:
        """Score from gnomAD transcript annotation + GTEx expression.

        HC LoF = high-confidence loss-of-function (strong pathogenic signal).
        High mean expression = variant in actively expressed gene.
        """
        if not data or not data.get("found"):
            return None
        lof = data.get("lof")
        mean_expr = data.get("mean_expression")
        if lof == "HC":
            score = 0.80
            label = "gnomAD-tx: HC LoF"
        elif lof == "LC":
            score = 0.55
            label = "gnomAD-tx: LC LoF"
        elif mean_expr is not None and mean_expr > 0.5:
            score = 0.45
            label = f"gnomAD-tx: high expression ({mean_expr:.2f})"
        elif mean_expr is not None and mean_expr > 0.1:
            score = 0.35
            label = f"gnomAD-tx: moderate expression ({mean_expr:.2f})"
        else:
            return None
        return SourceEvidence(
            source="gnomad_tx", score=score,
            weight=_SOURCE_WEIGHTS["gnomad_tx"],
            label=label,
            raw_value=data.get("lof") or data.get("mean_expression"),
        )

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
