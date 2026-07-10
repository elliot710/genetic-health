import logging
import re
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..db.models import (
    AnalysisVariant, GeneticMarker, SharedVariantAnnotation,
    ClinVarGeneStats, ClinVarGeneCondition,
)

logger = logging.getLogger(__name__)

_NO_CALL_GENOTYPES = frozenset({'./.', '.|.', '--', '00', 'NC'})


async def build_annotation_maps(
    db: AsyncSession,
    primary_analysis_id: int,
) -> Dict[str, Any]:
    annotation_rows = (await db.execute(
        select(
            GeneticMarker.rsid, GeneticMarker.ref_allele, GeneticMarker.alt_alleles,
            SharedVariantAnnotation.alpha_missense_data, SharedVariantAnnotation.clinvar_data,
            SharedVariantAnnotation.clinvar_local_data, SharedVariantAnnotation.alphafold_data,
            SharedVariantAnnotation.pharmgkb_data, SharedVariantAnnotation.ensembl_data,
        )
        .select_from(AnalysisVariant)
        .join(GeneticMarker, AnalysisVariant.marker_id == GeneticMarker.id)
        .outerjoin(SharedVariantAnnotation, SharedVariantAnnotation.marker_id == GeneticMarker.id)
        .where(AnalysisVariant.analysis_id == primary_analysis_id)
    )).all()

    am_map: Dict[str, Any] = {}
    cv_count_map: Dict[str, int] = {}
    allele_string_map: Dict[str, str] = {}
    pharmgkb_map: Dict[str, Any] = {}

    for row in annotation_rows:
        _populate_am_map(row, am_map)
        _populate_cv_count_map(row, cv_count_map)
        _populate_allele_string_map(row, allele_string_map)
        _populate_pharmgkb_map(row, pharmgkb_map)

    return {
        'annotation_rows': annotation_rows,
        'am_map': am_map,
        'cv_count_map': cv_count_map,
        'allele_string_map': allele_string_map,
        'pharmgkb_map': pharmgkb_map,
    }


def _populate_am_map(row, am_map: Dict) -> None:
    am = row.alpha_missense_data
    if isinstance(am, dict) and am.get('found'):
        am_map[row.rsid] = {"score": am.get('am_pathogenicity'), "classification": am.get('am_class')}


def _populate_cv_count_map(row, cv_count_map: Dict) -> None:
    cv = row.clinvar_data
    if isinstance(cv, dict) and cv.get('found'):
        count = cv.get('count', 0)
        if count > 0:
            cv_count_map[row.rsid] = count


def _populate_allele_string_map(row, allele_string_map: Dict) -> None:
    ensembl = row.ensembl_data
    if isinstance(ensembl, dict):
        data_list = ensembl.get('data', [])
        if data_list and isinstance(data_list, list):
            allele_str = data_list[0].get('allele_string', '')
            if allele_str and '/' in allele_str:
                allele_string_map[row.rsid] = allele_str
                return
    if row.rsid not in allele_string_map:
        ref_a, alt_a = row.ref_allele, row.alt_alleles
        if ref_a and alt_a:
            allele_string_map[row.rsid] = f"{ref_a}/{alt_a}"
        elif ref_a:
            allele_string_map[row.rsid] = ref_a


def _populate_pharmgkb_map(row, pharmgkb_map: Dict) -> None:
    pgkb = row.pharmgkb_data
    if not (isinstance(pgkb, dict) and pgkb.get('found')):
        return
    entry: Dict[str, Any] = {"gene": pgkb.get('gene', '')}
    variants_data = pgkb.get('variants', [])
    if isinstance(variants_data, list):
        haplotypes = [
            v.get('haplotype') or v.get('star_allele')
            for v in variants_data if v.get('haplotype') or v.get('star_allele')
        ]
        if haplotypes:
            entry['haplotypes'] = haplotypes[:4]
    guidelines = pgkb.get('guidelines', [])
    if isinstance(guidelines, list) and guidelines:
        g = guidelines[0]
        entry['cpic_guideline'] = g.get('name') or g.get('url') or ''
    if isinstance(variants_data, list) and variants_data:
        top = variants_data[0]
        entry['phenotype'] = top.get('phenotype') or top.get('function') or ''
        entry['star_allele'] = top.get('star_allele') or top.get('haplotype') or ''
    pharmgkb_map[row.rsid] = entry


async def build_genotype_and_gene_maps(
    db: AsyncSession,
    analysis_ids: List[int],
    panel_rsids: set,
) -> tuple:
    genotype_map: Dict[str, str] = {}
    gene_symbol_map: Dict[str, str] = {}
    if not panel_rsids:
        return genotype_map, gene_symbol_map

    genotype_query = await db.execute(
        select(GeneticMarker.rsid, AnalysisVariant.genotype)
        .select_from(AnalysisVariant)
        .join(GeneticMarker, AnalysisVariant.marker_id == GeneticMarker.id)
        .where(AnalysisVariant.analysis_id.in_(analysis_ids))
        .where(GeneticMarker.rsid.in_(panel_rsids))
        .where(AnalysisVariant.genotype.isnot(None))
        .where(AnalysisVariant.genotype != '')
        .where(AnalysisVariant.genotype.notin_(list(_NO_CALL_GENOTYPES)))
    )
    for row in genotype_query.all():
        genotype_map[row.rsid] = row.genotype

    gs_query = await db.execute(
        select(GeneticMarker.rsid, GeneticMarker.gene_symbol)
        .where(GeneticMarker.rsid.in_(panel_rsids))
        .where(GeneticMarker.gene_symbol.isnot(None))
        .where(GeneticMarker.gene_symbol != '')
    )
    for row in gs_query.all():
        gene_symbol_map[row.rsid] = row.gene_symbol

    return genotype_map, gene_symbol_map


def build_alphafold_map(gene_symbol_map: Dict[str, str], panel_rsids: set) -> Dict[str, Any]:
    alphafold_map: Dict[str, Any] = {}
    try:
        from ..services.alphafold_local import get_alphafold_local_service
        af_svc = get_alphafold_local_service()
        if not (af_svc.available and gene_symbol_map):
            return alphafold_map
        panel_gene_rsids = {r: g for r, g in gene_symbol_map.items() if r in panel_rsids}
        unique_genes = list(set(panel_gene_rsids.values()))
        if not unique_genes:
            return alphafold_map
        gene_results = af_svc.bulk_lookup_genes(unique_genes)
        for rsid, gene in panel_gene_rsids.items():
            af_data = gene_results.get(gene)
            if af_data and af_data.get('found'):
                alphafold_map[rsid] = {
                    "confidence": af_data.get('global_confidence'),
                    "high_confidence_pct": af_data.get('plddt_very_high', 0) or 0,
                    "low_confidence_pct": af_data.get('plddt_very_low', 0) or 0,
                    "protein_name": af_data.get('protein_name'),
                }
    except Exception:
        logger.warning("Failed to build alphafold_map from local DB")
    return alphafold_map


async def build_pathogenicity_map(
    db: AsyncSession, primary_analysis_id: int, panel_rsids: set
) -> Dict[str, Any]:
    pathogenicity_map: Dict[str, Any] = {}
    if not panel_rsids:
        return pathogenicity_map
    try:
        from ..services.scoring_engine import get_scoring_engine
        scoring_engine = get_scoring_engine()
        scoring_rows = (await db.execute(
            select(
                GeneticMarker.rsid,
                SharedVariantAnnotation.ensembl_data,
                SharedVariantAnnotation.clinvar_data,
                SharedVariantAnnotation.clinvar_local_data,
                SharedVariantAnnotation.alpha_missense_data,
                SharedVariantAnnotation.gnomad_data,
            )
            .select_from(AnalysisVariant)
            .join(GeneticMarker, AnalysisVariant.marker_id == GeneticMarker.id)
            .join(SharedVariantAnnotation, SharedVariantAnnotation.marker_id == GeneticMarker.id)
            .where(AnalysisVariant.analysis_id == primary_analysis_id)
            .where(GeneticMarker.rsid.in_(panel_rsids))
        )).all()
        for row in scoring_rows:
            _score_single_variant(row, scoring_engine, pathogenicity_map)
    except Exception:
        logger.warning("Failed to compute pathogenicity_map – skipping")
    return pathogenicity_map


def _score_single_variant(row, scoring_engine, pathogenicity_map: Dict) -> None:
    annotations = {k: v for k, v in [
        ("ensembl", row.ensembl_data), ("clinvar", row.clinvar_data),
        ("clinvar_local", row.clinvar_local_data),
        ("alpha_missense", row.alpha_missense_data), ("gnomad", row.gnomad_data),
    ] if v}
    if not annotations:
        return
    result = scoring_engine.score_variant(annotations)
    if result.get("evidence_count", 0) > 0:
        pathogenicity_map[row.rsid] = {
            "score": round(result["composite_score"] * 100),
            "classification": result.get("classification", "unknown"),
            "confidence": result.get("confidence", "none"),
            "evidence_count": result.get("evidence_count", 0),
        }


def backfill_clinvar_significance(dashboard_data: Dict[str, Any], annotation_rows) -> None:
    try:
        clinvar_sig_map = _build_clinvar_sig_map(annotation_rows)
        for hr_item in dashboard_data.get("health_risks", []):
            for v in (hr_item.get("associated_variants") or []):
                sig = clinvar_sig_map.get(v)
                if sig:
                    hr_item["clinical_significance"] = sig
                    break
    except Exception:
        logger.warning("Failed to backfill clinical_significance – skipping")


def _build_clinvar_sig_map(annotation_rows) -> Dict[str, str]:
    clinvar_sig_map: Dict[str, str] = {}
    for row in annotation_rows:
        cv_local = row.clinvar_local_data
        if not isinstance(cv_local, dict):
            continue
        sigs: list = []
        for entry in cv_local.get("entries", []):
            for sig in entry.get("clinical_significance", []):
                if sig and sig not in sigs:
                    sigs.append(sig)
        if sigs:
            clinvar_sig_map[row.rsid] = "; ".join(sigs)
        elif cv_local.get("clinical_significance"):
            raw = cv_local["clinical_significance"]
            clinvar_sig_map[row.rsid] = raw if isinstance(raw, str) else "; ".join(raw)
    return clinvar_sig_map


async def build_gene_stats_map(
    db: AsyncSession,
    dashboard_data: Dict[str, Any],
    gene_symbol_map: Dict[str, str],
) -> Dict[str, Any]:
    panel_genes = _collect_panel_genes(dashboard_data, gene_symbol_map)
    if not panel_genes:
        return {}
    try:
        return await _query_gene_stats(db, panel_genes)
    except Exception:
        logger.warning("Failed to build gene_stats_map – skipping")
        return {}


def _collect_panel_genes(dashboard_data: Dict, gene_symbol_map: Dict) -> set:
    panel_genes: set = set()
    for panel_key in ("health_risks", "rare_mutations", "drug_responses",
                      "uncommon_mutations", "methylation_profiles", "detoxification_profiles"):
        for item in dashboard_data.get(panel_key, []):
            if item.get("gene"):
                panel_genes.add(item["gene"])
    for item in dashboard_data.get("carrier_status", []):
        if item.get("gene"):
            panel_genes.add(item["gene"])
        else:
            m = re.search(r'\(([A-Z][A-Z0-9]{1,9})\)\s*$', item.get("condition", ""))
            if m:
                panel_genes.add(m.group(1))
        for v in (item.get("associated_variants") or []):
            if isinstance(v, str) and v in gene_symbol_map:
                panel_genes.add(gene_symbol_map[v])
                if not item.get("gene"):
                    item["gene"] = gene_symbol_map[v]
    panel_genes.update(gene_symbol_map.values())
    return panel_genes


async def _query_gene_stats(db: AsyncSession, panel_genes: set) -> Dict[str, Any]:
    gene_stats_map: Dict[str, Any] = {}
    stats_rows = (await db.execute(
        select(ClinVarGeneStats).where(ClinVarGeneStats.gene.in_(panel_genes))
    )).scalars().all()
    stats_by_gene = {s.gene: s for s in stats_rows}
    cond_rows = (await db.execute(
        select(ClinVarGeneCondition).where(ClinVarGeneCondition.gene.in_(panel_genes))
    )).scalars().all()
    conditions_by_gene: Dict[str, list] = {}
    for c in cond_rows:
        conditions_by_gene.setdefault(c.gene, []).append({
            "disease_name": c.disease_name, "disease_mim": c.disease_mim, "source_id": c.source_id,
        })
    for gene in panel_genes:
        stats = stats_by_gene.get(gene)
        if stats:
            gene_stats_map[gene] = {
                "pathogenic_lp": stats.pathogenic_likely_pathogenic or 0,
                "vus": stats.uncertain_significance or 0,
                "total_submissions": stats.total_submissions or 0,
                "total_alleles": stats.total_alleles or 0,
                "with_conflicts": stats.with_conflicts or 0,
                "gene_mim": stats.gene_mim,
                "conditions": conditions_by_gene.get(gene, []),
            }
    return gene_stats_map
