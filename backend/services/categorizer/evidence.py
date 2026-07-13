"""Evidence extraction: raw multi-source annotations -> SourceEvidence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from backend.services.categorizer.models import *  # noqa: F401,F403


def extract_evidence(annotations: Dict[str, Any]) -> List[SourceEvidence]:
    """Extract standardized evidence from all annotation sources.

    `annotations` is the dict stored in shared_variant_annotations columns
    or the response_data from variant lookup — each key is a source name
    mapping to its JSON payload.
    """
    evidence: List[SourceEvidence] = []

    # ── ClinVar local ───────────────────────────────────────────────
    cv_local = annotations.get("clinvar_local_data") or annotations.get("clinvar_local") or {}
    if isinstance(cv_local, dict) and cv_local.get("found"):
        sigs = cv_local.get("clinical_significances", [])
        conds = cv_local.get("conditions", [])
        genes = cv_local.get("genes", [])
        reviews = cv_local.get("review_statuses", [])
        # Filter noise conditions
        clean_conds = [c for c in conds
                       if c.lower().strip() not in ("not provided", "not specified", "see cases", "")]
        ev = SourceEvidence(
            source_name="clinvar_local",
            gene=genes[0] if genes else None,
            conditions=clean_conds,
            clinical_significances=[s.lower() for s in sigs],
            review_status=reviews[0] if reviews else None,
        )
        # Derive pathogenicity score from significance
        sig_lower = " ".join(s.lower() for s in sigs)
        if any(k in sig_lower for k in ("pathogenic",)):
            ev.pathogenicity_score = 0.9 if "likely" not in sig_lower else 0.75
        elif "risk" in sig_lower or "association" in sig_lower:
            ev.pathogenicity_score = 0.5
        elif any(k in sig_lower for k in ("benign",)):
            ev.pathogenicity_score = 0.1 if "likely" not in sig_lower else 0.15
        else:
            ev.pathogenicity_score = 0.4  # VUS
        evidence.append(ev)

    # ── ClinVar API ─────────────────────────────────────────────────
    cv_api = annotations.get("clinvar_data") or annotations.get("clinvar") or {}
    if isinstance(cv_api, dict) and cv_api.get("found"):
        entries = cv_api.get("entries", [])
        sigs = []
        conds = []
        for entry in entries:
            sigs.extend(entry.get("clinical_significance", []))
            conds.extend(entry.get("conditions", []))
        clean_conds = [c for c in conds
                       if c.lower().strip() not in ("not provided", "not specified", "see cases", "")]
        if sigs or clean_conds:
            ev = SourceEvidence(
                source_name="clinvar_api",
                conditions=clean_conds,
                clinical_significances=[s.lower() for s in sigs],
            )
            sig_lower = " ".join(s.lower() for s in sigs)
            if "pathogenic" in sig_lower:
                ev.pathogenicity_score = 0.85
            elif "benign" in sig_lower:
                ev.pathogenicity_score = 0.1
            evidence.append(ev)

    # ── Ensembl VEP ─────────────────────────────────────────────────
    ensembl = annotations.get("ensembl_data") or annotations.get("ensembl") or {}
    if isinstance(ensembl, dict) and ensembl.get("found"):
        data_list = ensembl.get("data", [])
        entry = data_list[0] if isinstance(data_list, list) and data_list else (
            data_list if isinstance(data_list, dict) else None
        )
        if entry:
            tc = entry.get("transcript_consequences", [])
            gene = tc[0].get("gene_symbol") if tc else None
            consequence = entry.get("most_severe_consequence", "")
            # Get best SIFT/PolyPhen from transcript consequences
            best_sift = None
            best_polyphen = None
            for t in tc:
                s = t.get("sift_score")
                p = t.get("polyphen_score")
                if s is not None and (best_sift is None or s < best_sift):
                    best_sift = s
                if p is not None and (best_polyphen is None or p > best_polyphen):
                    best_polyphen = p
            # Map consequence to impact
            _IMPACT = {
                "transcript_ablation": "HIGH", "splice_acceptor_variant": "HIGH",
                "splice_donor_variant": "HIGH", "stop_gained": "HIGH",
                "frameshift_variant": "HIGH", "stop_lost": "HIGH",
                "start_lost": "HIGH",
                "missense_variant": "MODERATE", "inframe_insertion": "MODERATE",
                "inframe_deletion": "MODERATE", "protein_altering_variant": "MODERATE",
                "splice_region_variant": "MODERATE",
                "synonymous_variant": "LOW", "stop_retained_variant": "LOW",
                "intron_variant": "MODIFIER", "upstream_gene_variant": "MODIFIER",
                "downstream_gene_variant": "MODIFIER",
            }
            impact = _IMPACT.get(consequence, "MODIFIER")
            # Pathogenicity from VEP predictors
            path_score = None
            if best_polyphen is not None:
                path_score = best_polyphen  # PolyPhen: 0=benign, 1=damaging
            elif best_sift is not None:
                path_score = 1.0 - best_sift  # SIFT: 0=damaging, 1=tolerated → invert
            elif impact == "HIGH":
                path_score = 0.8
            elif impact == "MODERATE":
                path_score = 0.5

            ev = SourceEvidence(
                source_name="ensembl_vep",
                gene=gene,
                consequence=consequence,
                sift_score=best_sift,
                polyphen_score=best_polyphen,
                pathogenicity_score=path_score,
                impact=impact,
            )
            evidence.append(ev)

    # ── AlphaMissense ───────────────────────────────────────────────
    am = annotations.get("alpha_missense_data") or annotations.get("alpha_missense") or {}
    if isinstance(am, dict) and am.get("found"):
        am_score = am.get("am_pathogenicity")
        if am_score is not None:
            evidence.append(SourceEvidence(
                source_name="alpha_missense",
                pathogenicity_score=float(am_score),
            ))

    # ── gnomAD ──────────────────────────────────────────────────────
    gnomad = annotations.get("gnomad_data") or annotations.get("gnomad_local") or {}
    if isinstance(gnomad, dict) and gnomad.get("found"):
        gene = gnomad.get("gene")
        af = gnomad.get("af") or gnomad.get("allele_frequency")
        consequence = gnomad.get("consequence")
        impact = gnomad.get("impact")
        cadd = gnomad.get("cadd", {})
        cadd_phred = cadd.get("phred") if isinstance(cadd, dict) else None
        # CADD ≥ 20 → top 1% most deleterious, ≥ 30 → top 0.1%
        path_from_cadd = None
        if cadd_phred is not None:
            if cadd_phred >= 30:
                path_from_cadd = 0.9
            elif cadd_phred >= 20:
                path_from_cadd = 0.7
            elif cadd_phred >= 15:
                path_from_cadd = 0.5
        evidence.append(SourceEvidence(
            source_name="gnomad",
            gene=gene,
            consequence=consequence,
            impact=impact,
            allele_frequency=float(af) if af else None,
            pathogenicity_score=path_from_cadd,
        ))

    # ── SNPedia ─────────────────────────────────────────────────────
    snpedia = annotations.get("snpedia_data") or annotations.get("snpedia") or {}
    if isinstance(snpedia, dict) and snpedia.get("found"):
        evidence.append(SourceEvidence(source_name="snpedia"))

    # ── 1000 Genomes ────────────────────────────────────────────────
    tg = annotations.get("thousand_genomes_data") or annotations.get("thousand_genomes") or {}
    if isinstance(tg, dict) and tg.get("found"):
        af = tg.get("global_af") or tg.get("allele_frequency")
        evidence.append(SourceEvidence(
            source_name="1000genomes",
            allele_frequency=float(af) if af else None,
        ))

    # ── gnomAD gene constraint ──────────────────────────────────────
    gnomad_tx = annotations.get("gnomad_tx_data") or {}
    if isinstance(gnomad_tx, dict) and gnomad_tx.get("found"):
        evidence.append(SourceEvidence(source_name="gnomad_tx"))

    return evidence
