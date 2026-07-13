"""Per-source scoring methods for the ScoringEngine, factored into a mixin.

Behaviour-identical to the original in-class methods; ScoringEngine subclasses
this so ``self._score_*`` and the shared ``self._*_to_score`` helpers resolve
through the normal MRO.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from backend.services.scoring.models import SourceEvidence, _SOURCE_WEIGHTS


class _SourceScorers:
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

        # Allele frequency (rarity as pathogenicity evidence).
        # NOTE: the main gnomAD CADD file carries no AF column — `af` here is
        # populated by the gnomAD v2 exome fallback in local_annotation
        # run_all_lookups (which writes results.gnomad[rsid]['af'] = af_nfe).
        # So gnomad_af evidence is effectively sourced from gnomad_v2; when v2
        # has no coverage for a variant, af is None and no AF evidence is added
        # (absence is not scored as 0). This is correct — do not synthesize AF
        # from the CADD path, which is conservation/pathogenicity-only.
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
