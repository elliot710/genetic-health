from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    GeneticMarker, SharedVariantAnnotation,
)
from backend.services.genetic_api_service import GeneticAPIService


def build_clinical_summary_from_cache(
    cached: SharedVariantAnnotation, rsid: str, gene: Optional[str]
) -> Dict[str, Any]:
    summary = _empty_clinical_summary(rsid, gene)

    if _is_dict_found(cached.clinvar_data):
        summary["sources"].append("clinvar")
        summary["clinical_significance"] = "Reported in ClinVar"
        summary["clinvar_ids"] = cached.clinvar_data.get("ids", [])

    _extract_ensembl_summary(cached.ensembl_data, summary)

    if _is_dict_found(cached.pharmgkb_data):
        summary["sources"].append("clinpgx")

    if _is_dict_found(cached.snpedia_data):
        summary["sources"].append("snpedia")

    am = cached.alpha_missense_data
    if isinstance(am, dict) and am.get("found"):
        summary["alpha_missense"] = {
            "am_pathogenicity": am.get("am_pathogenicity"),
            "am_class": am.get("am_class"),
        }

    return summary


async def build_clinical_summary(
    rsid: str, gene: Optional[str], refresh: bool, db: AsyncSession
) -> Dict[str, Any]:
    summary = _empty_clinical_summary(rsid, gene)

    if not refresh:
        result = await db.execute(
            select(SharedVariantAnnotation).where(
                SharedVariantAnnotation.rsid == rsid
            )
        )
        cached = result.scalar_one_or_none()
        if cached and _has_any_annotation(cached):
            return build_clinical_summary_from_cache(cached, rsid, gene)

    raw = await _fetch_and_persist_annotations(rsid, db)
    return _build_summary_from_raw(raw, summary)


async def _fetch_and_persist_annotations(
    rsid: str, db: AsyncSession
) -> Dict[str, Any]:
    async with GeneticAPIService() as api_service:
        raw_ann = await api_service.annotate_variant(rsid)
    raw = raw_ann.get("annotations", {}) if raw_ann else {}
    if not raw:
        return raw

    try:
        existing = await db.execute(
            select(SharedVariantAnnotation).where(
                SharedVariantAnnotation.rsid == rsid
            )
        )
        existing_ann = existing.scalar_one_or_none()
        if existing_ann:
            _update_existing_fields(existing_ann, raw)
        else:
            await _create_new_annotation(rsid, raw, db)
        await db.commit()
    except Exception:
        pass
    return raw


def _update_existing_fields(ann: SharedVariantAnnotation, raw: dict):
    ann.ensembl_data = raw.get("ensembl") or ann.ensembl_data
    ann.clinvar_data = raw.get("clinvar") or ann.clinvar_data
    ann.pharmgkb_data = raw.get("clinpgx") or ann.pharmgkb_data
    ann.snpedia_data = raw.get("snpedia") or ann.snpedia_data
    ann.litvar_data = raw.get("litvar") or ann.litvar_data


async def _create_new_annotation(rsid: str, raw: dict, db: AsyncSession):
    marker_result = await db.execute(
        select(GeneticMarker).where(GeneticMarker.rsid == rsid)
    )
    marker = marker_result.scalar_one_or_none()
    db.add(SharedVariantAnnotation(
        rsid=rsid,
        marker_id=marker.id if marker else None,
        ensembl_data=raw.get("ensembl"),
        clinvar_data=raw.get("clinvar"),
        pharmgkb_data=raw.get("clinpgx"),
        snpedia_data=raw.get("snpedia"),
        litvar_data=raw.get("litvar"),
    ))


def _build_summary_from_raw(raw: dict, summary: dict) -> dict:
    clinvar = raw.get("clinvar", {})
    if _is_dict_found(clinvar):
        summary["sources"].append("clinvar")
        summary["clinical_significance"] = "Reported in ClinVar"
        summary["clinvar_ids"] = clinvar.get("ids", [])

    _extract_ensembl_summary(raw.get("ensembl", {}), summary)

    if _is_dict_found(raw.get("clinpgx", {})):
        summary["sources"].append("clinpgx")

    if _is_dict_found(raw.get("snpedia", {})):
        summary["sources"].append("snpedia")

    return summary


def _empty_clinical_summary(rsid: str, gene: Optional[str]) -> Dict[str, Any]:
    return {
        "rsid": rsid,
        "gene": gene,
        "clinical_significance": "unknown",
        "population_frequency": None,
        "drug_responses": [],
        "literature_count": 0,
        "sources": [],
    }


def _is_dict_found(data) -> bool:
    return isinstance(data, dict) and data.get("found", False)


def _has_any_annotation(cached: SharedVariantAnnotation) -> bool:
    return bool(
        cached.ensembl_data or cached.clinvar_data
        or cached.pharmgkb_data or cached.snpedia_data
    )


def _extract_ensembl_summary(ensembl: Any, summary: dict):
    if not _is_dict_found(ensembl):
        return
    summary["sources"].append("ensembl")
    data = ensembl.get("data", [])
    if not (isinstance(data, list) and data):
        return
    vep = data[0]
    freqs = vep.get("colocated_variants", [{}])
    if freqs:
        freq_data = freqs[0].get("frequencies", {})
        if freq_data:
            summary["population_frequency"] = freq_data
    consequences = vep.get("most_severe_consequence", "")
    if consequences:
        summary["consequence"] = consequences.replace("_", " ")
