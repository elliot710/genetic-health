import logging
from typing import Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    AnalysisVariant, AnnotationSourceConfig, DashboardCache,
    GeneticAnalysis, GeneticMarker, SharedVariantAnnotation,
)
from backend.services.genetic_api_service import GeneticAPIService

logger = logging.getLogger(__name__)


async def load_or_fetch_annotation(
    rsid: str, refresh: bool, db: AsyncSession, current_user
) -> Tuple[Optional[SharedVariantAnnotation], bool]:
    if not refresh:
        result = await db.execute(
            select(SharedVariantAnnotation).where(
                SharedVariantAnnotation.rsid == rsid
            )
        )
        annotation = result.scalar_one_or_none()
        if annotation:
            return annotation, True

    try:
        annotation = await _fetch_fresh_annotation(
            rsid, refresh, db, current_user
        )
        return annotation, False
    except Exception:
        return None, False


async def _fetch_fresh_annotation(rsid, refresh, db, current_user):
    marker_result = await db.execute(
        select(GeneticMarker).where(GeneticMarker.rsid == rsid)
    )
    marker = marker_result.scalar_one_or_none()
    async with GeneticAPIService() as api_service:
        live = await api_service.annotate_variant(rsid)
    raw = live.get("annotations", {})

    if refresh:
        annotation = await _update_existing_annotation(
            rsid, raw, db, current_user
        )
        if annotation:
            return annotation

    annotation = SharedVariantAnnotation(
        rsid=rsid,
        marker_id=marker.id if marker else None,
        ensembl_data=raw.get("ensembl"),
        clinvar_data=raw.get("clinvar"),
        pharmgkb_data=raw.get("clinpgx"),
        snpedia_data=raw.get("snpedia"),
        litvar_data=raw.get("litvar"),
    )
    db.add(annotation)
    await db.commit()
    await db.refresh(annotation)
    return annotation


async def _update_existing_annotation(rsid, raw, db, current_user):
    existing = await db.execute(
        select(SharedVariantAnnotation).where(
            SharedVariantAnnotation.rsid == rsid
        )
    )
    existing_ann = existing.scalar_one_or_none()
    if not existing_ann:
        return None
    existing_ann.ensembl_data = raw.get("ensembl")
    existing_ann.clinvar_data = raw.get("clinvar")
    existing_ann.pharmgkb_data = raw.get("clinpgx")
    existing_ann.snpedia_data = raw.get("snpedia")
    existing_ann.litvar_data = raw.get("litvar")
    await db.execute(
        DashboardCache.__table__.delete().where(
            DashboardCache.user_id == current_user.id
        )
    )
    await db.commit()
    await db.refresh(existing_ann)
    return existing_ann


async def attach_user_genotype(
    rsid: str, user_id: int, db: AsyncSession, response: dict
):
    try:
        geno_result = await db.execute(
            select(AnalysisVariant.genotype)
            .join(GeneticMarker, GeneticMarker.id == AnalysisVariant.marker_id)
            .join(GeneticAnalysis, GeneticAnalysis.id == AnalysisVariant.analysis_id)
            .where(
                GeneticMarker.rsid == rsid,
                GeneticAnalysis.user_id == user_id,
                GeneticAnalysis.deleted_at.is_(None),
            )
            .order_by(GeneticAnalysis.id.desc())
            .limit(1)
        )
        user_genotype = geno_result.scalar_one_or_none()
        if user_genotype:
            response["user_genotype"] = user_genotype
    except Exception:
        pass


BQ_COLUMNS = {
    "chembl": "chembl_data",
    "fda_drug": "fda_drug_data",
    "alphafold": "alphafold_data",
}


async def enrich_bigquery(
    annotation, response: dict, gene_symbol: Optional[str], db: AsyncSession
):
    enabled_bq = await _get_enabled_bq_sources(set(BQ_COLUMNS), db)
    needs_fetch = _check_bq_cache(annotation, response, enabled_bq)

    if not needs_fetch or not gene_symbol:
        return
    await _fetch_bq_data(annotation, response, gene_symbol, needs_fetch, db)


def _check_bq_cache(annotation, response: dict, enabled: set) -> set:
    needs_fetch: set = set()
    for src in enabled:
        cached = getattr(annotation, BQ_COLUMNS[src], None)
        if cached and isinstance(cached, dict):
            response[src] = cached
        else:
            needs_fetch.add(src)
    return needs_fetch


async def _fetch_bq_data(annotation, response, gene_symbol, needs_fetch, db):
    try:
        from backend.services.bq_public import get_bq_public_service
        enrichment = await get_bq_public_service().enrich_variant(
            gene_symbol=gene_symbol, enabled_sources=needs_fetch,
        )
        dirty = False
        for src, data in enrichment.items():
            if src in BQ_COLUMNS and data:
                setattr(annotation, BQ_COLUMNS[src], data)
                response[src] = data
                dirty = True
        if dirty:
            await db.commit()
    except Exception as e:
        logger.warning("BigQuery enrichment failed: %s", e)


async def _get_enabled_bq_sources(bq_sources: set, db: AsyncSession) -> set:
    try:
        src_result = await db.execute(
            select(
                AnnotationSourceConfig.source_name,
                AnnotationSourceConfig.is_enabled,
            ).where(AnnotationSourceConfig.source_name.in_(list(bq_sources)))
        )
        src_rows = src_result.all()
        if src_rows:
            return {name for name, enabled in src_rows if enabled}
    except Exception:
        pass
    return bq_sources


async def attach_open_targets(
    annotation, response: dict, scoring_annotations: dict,
    gene_symbol: Optional[str], db: AsyncSession,
):
    ot_data = await _fetch_open_targets(annotation, gene_symbol, db)
    if not (ot_data and isinstance(ot_data, dict) and ot_data.get("found")):
        return

    response["open_targets"] = {
        "found": True,
        "source": "open_targets",
        "gene_symbol": ot_data.get("gene_symbol"),
        "ensembl_id": ot_data.get("ensembl_id"),
        "associations": ot_data.get("associations", [])[:10],
        "top_disease": ot_data.get("top_disease"),
        "max_score": ot_data.get("max_score"),
        "has_strong_genetic_evidence": ot_data.get(
            "has_strong_genetic_evidence", False
        ),
    }
    if "open_targets" not in scoring_annotations:
        scoring_annotations["open_targets"] = ot_data
        from backend.services.scoring_engine import get_scoring_engine
        response["pathogenicity_score"] = get_scoring_engine().score_variant(
            scoring_annotations
        )


async def _fetch_open_targets(annotation, gene_symbol, db):
    has_cached = (
        annotation.open_targets_data
        and isinstance(annotation.open_targets_data, dict)
        and annotation.open_targets_data.get("found")
    )
    if gene_symbol and not has_cached:
        try:
            from backend.services.open_targets_service import (
                get_open_targets_service,
            )
            ot_data = await get_open_targets_service().lookup_by_gene(
                gene_symbol
            )
            annotation.open_targets_data = ot_data
            await db.commit()
            return ot_data
        except Exception:
            return {}
    return annotation.open_targets_data or {}

