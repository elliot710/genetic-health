"""Startup/batch data loaders that populate the categorizer maps and enrich mappings from the DB.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from backend.services.categorizer.models import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Startup loader — populates GENE_CATEGORY_MAP, _CONDITION_CATEGORY_KW,
# and _SEVERE_EXCLUSION_KW from CategoryRule rows in the database.
# Call once from the application lifespan (main.py) after the DB is ready.
# ---------------------------------------------------------------------------

async def init_categorizer_data() -> None:
    """Load all domain data for the categorizer from the CategoryRule DB table.

    Three rule types are consumed:
    - ``gene_list``                 → GENE_CATEGORY_MAP
    - ``clinvar_condition_keyword`` → _CONDITION_CATEGORY_KW
    - ``lifestyle_exclude_keyword`` → _SEVERE_EXCLUSION_KW
    """
    from sqlalchemy import select
    from backend.db.database import async_session_factory
    from backend.db.models import CategoryRule

    async with async_session_factory() as session:
        result = await session.execute(
            select(CategoryRule.rule_type, CategoryRule.category, CategoryRule.rule_value)
            .where(CategoryRule.is_active == True)
            .where(CategoryRule.rule_type.in_([
                "gene_list",
                "clinvar_condition_keyword",
                "lifestyle_exclude_keyword",
            ]))
        )
        rows = result.all()

    gene_map: Dict[str, List[str]] = {}
    cond_kw: Dict[str, List[str]] = {}
    excl_kw: Set[str] = set()

    for rule_type, category, rule_value in rows:
        if rule_type == "gene_list":
            for gene in rule_value.split(","):
                gene = gene.strip().upper()
                if gene:
                    if gene not in gene_map:
                        gene_map[gene] = []
                    if category not in gene_map[gene]:
                        gene_map[gene].append(category)
        elif rule_type == "clinvar_condition_keyword":
            kw = rule_value.strip().lower()
            if kw:
                cond_kw.setdefault(category, [])
                if kw not in cond_kw[category]:
                    cond_kw[category].append(kw)
        elif rule_type == "lifestyle_exclude_keyword":
            excl_kw.add(rule_value.strip().lower())

    GENE_CATEGORY_MAP.clear()
    GENE_CATEGORY_MAP.update(gene_map)
    _CONDITION_CATEGORY_KW.clear()
    _CONDITION_CATEGORY_KW.update(cond_kw)
    _SEVERE_EXCLUSION_KW.clear()
    _SEVERE_EXCLUSION_KW.update(excl_kw)

    logger.info(
        "Categorizer data loaded from DB: %d genes, %d condition keyword rules, %d exclusion keywords",
        len(GENE_CATEGORY_MAP),
        sum(len(v) for v in _CONDITION_CATEGORY_KW.values()),
        len(_SEVERE_EXCLUSION_KW),
    )


# ---------------------------------------------------------------------------
# Async helpers for pre-loading condition hints from DB
# ---------------------------------------------------------------------------

async def load_condition_hints(genes: List[str]) -> Dict[str, Any]:
    """Pre-load gene→condition and gene→description mappings from DB.

    Used by callers of categorize_variant() to provide multi-source
    condition naming when ClinVar variant-level conditions are absent.

    Returns:
        Dict with keys:
        - "gene_conditions": Dict[str, List[str]] — gene → disease names
        - "gene_descriptions": Dict[str, str] — gene → Ensembl description
    """
    if not genes:
        return {"gene_conditions": {}, "gene_descriptions": {}}

    from sqlalchemy import select
    from backend.db.database import async_session_factory
    from backend.db.models import ClinVarGeneCondition, EnsemblGene

    gene_conditions: Dict[str, List[str]] = {}
    gene_descriptions: Dict[str, str] = {}

    _GARBAGE_DISEASES = frozenset({
        "not provided", "not specified", "see cases", "not applicable",
        "none", ".", "-", "",
    })

    async with async_session_factory() as session:
        # 1. ClinVarGeneCondition — gene↔disease associations
        result = await session.execute(
            select(ClinVarGeneCondition.gene, ClinVarGeneCondition.disease_name)
            .where(ClinVarGeneCondition.gene.in_(genes))
        )
        for gene_sym, disease in result.all():
            if not disease or disease.lower().strip() in _GARBAGE_DISEASES:
                continue
            # Prefer shorter, more specific names (sort later)
            gene_conditions.setdefault(gene_sym, []).append(disease.strip())

        # Deduplicate and sort by length (shorter = more specific usually)
        for g in gene_conditions:
            seen: set = set()
            unique = []
            for d in gene_conditions[g]:
                dl = d.lower()
                if dl not in seen:
                    seen.add(dl)
                    unique.append(d)
            gene_conditions[g] = sorted(unique, key=len)

        # 2. EnsemblGene — functional gene descriptions
        result = await session.execute(
            select(EnsemblGene.gene_symbol, EnsemblGene.description)
            .where(EnsemblGene.gene_symbol.in_(genes))
            .distinct()
        )
        for gene_sym, desc in result.all():
            if desc and gene_sym not in gene_descriptions:
                gene_descriptions[gene_sym] = desc

    return {
        "gene_conditions": gene_conditions,
        "gene_descriptions": gene_descriptions,
    }


async def enrich_generic_mappings(
    dry_run: bool = False,
    categories: Optional[List[str]] = None,
    revise_all: bool = False,
) -> Dict[str, Any]:
    """Update existing variant_mappings with proper conditions from all
    available sources.

    Multi-source resolution order:
    1. ClinVar variant-level conditions (clinvar_variants table)
    2. ClinVar gene-level conditions (clinvar_gene_conditions table)
    3. Ensembl gene descriptions (ensembl_genes table)

    By default only updates rows with generic names (ending in ' variant').
    When ``revise_all=True``, re-evaluates **every** active mapping and
    upgrades condition text when a higher-priority source provides a better
    name (ClinVar variant > ClinVar gene > Ensembl gene > current).
    Named conditions are never downgraded to generic ones.

    Args:
        dry_run: If True, return what would be updated without writing.
        categories: Optional list of categories to limit the update to.
        revise_all: If True, check ALL active mappings (not just generic).

    Returns:
        Dict with stats: total_checked, total_updated, by_category, by_source.
    """
    from sqlalchemy import select, update, text
    from backend.db.database import async_session_factory
    from backend.db.models import VariantMapping, ClinVarVariant, ClinVarGeneCondition, EnsemblGene

    stats = {
        "total_checked": 0,
        "total_updated": 0,
        "by_category": {},
        "by_source": {"clinvar_variant": 0, "clinvar_gene": 0, "ensembl_gene": 0},
        "examples": [],
    }

    _GARBAGE = frozenset({
        "not provided", "not specified", "see cases", "not applicable",
        "none", ".", "-", "", ".|.",
    })

    def _is_generic(condition: str) -> bool:
        return condition.endswith(" variant") or condition == "Unknown variant"

    async with async_session_factory() as session:
        # Load active mappings
        q = select(VariantMapping).where(
            VariantMapping.is_active == True,
            VariantMapping.map_type == "rsid",
        )
        if categories:
            q = q.where(VariantMapping.category.in_(categories))

        result = await session.execute(q)
        mappings = result.scalars().all()

        if revise_all:
            # Check every mapping with a data dict
            target_mappings = [m for m in mappings if isinstance(m.data, dict)]
        else:
            # Only generic-named mappings
            target_mappings = [
                m for m in mappings
                if isinstance(m.data, dict) and _is_generic(m.data.get("condition", ""))
            ]
        stats["total_checked"] = len(target_mappings)

        if not target_mappings:
            return stats

        # Collect all rsids and genes
        rsids = {m.key for m in target_mappings}
        genes = {m.data.get("gene", "") for m in target_mappings if m.data.get("gene")}

        # Helper: batch IN queries to avoid exceeding PG bind param limit
        BATCH = 30000

        # Source 1: ClinVar variant-level conditions
        cv_map: Dict[str, str] = {}
        if rsids:
            rsid_list = list(rsids)
            for i in range(0, len(rsid_list), BATCH):
                batch = rsid_list[i:i + BATCH]
                result = await session.execute(
                    select(ClinVarVariant.rsid, ClinVarVariant.conditions)
                    .where(ClinVarVariant.rsid.in_(batch))
                    .where(ClinVarVariant.conditions.isnot(None))
                )
                for rsid, raw_conds in result.all():
                    if rsid in cv_map:
                        continue
                    if raw_conds:
                        # Clean pipe-separated conditions
                        parts = raw_conds.replace(";", "|").split("|")
                        for part in parts:
                            cleaned = part.strip()
                            if cleaned and cleaned.lower() not in _GARBAGE:
                                cv_map[rsid] = cleaned
                                break

        # Source 2: ClinVar gene-level conditions
        gene_cond_map: Dict[str, str] = {}
        if genes:
            gene_list = list(genes)
            for i in range(0, len(gene_list), BATCH):
                batch = gene_list[i:i + BATCH]
                result = await session.execute(
                    select(ClinVarGeneCondition.gene, ClinVarGeneCondition.disease_name)
                    .where(ClinVarGeneCondition.gene.in_(batch))
                )
                for gene_sym, disease in result.all():
                    if gene_sym in gene_cond_map:
                        continue
                    if disease and disease.lower().strip() not in _GARBAGE:
                        gene_cond_map[gene_sym] = disease.strip()

        # Source 3: Ensembl gene descriptions
        gene_desc_map: Dict[str, str] = {}
        if genes:
            gene_list = list(genes)
            for i in range(0, len(gene_list), BATCH):
                batch = gene_list[i:i + BATCH]
                result = await session.execute(
                    select(EnsemblGene.gene_symbol, EnsemblGene.description)
                    .where(EnsemblGene.gene_symbol.in_(batch))
                    .distinct()
                )
                for gene_sym, desc in result.all():
                    if desc and gene_sym not in gene_desc_map:
                        clean = desc.split("[")[0].strip()
                        if clean:
                            gene_desc_map[gene_sym] = f"{clean.title()} variant"

        # Apply enrichment
        for mapping in target_mappings:
            rsid = mapping.key
            gene = mapping.data.get("gene", "")
            old_condition = mapping.data.get("condition", "")
            new_condition = None
            source_used = None

            # Priority chain
            if rsid in cv_map:
                new_condition = cv_map[rsid]
                source_used = "clinvar_variant"
            elif gene in gene_cond_map:
                new_condition = gene_cond_map[gene]
                source_used = "clinvar_gene"
            elif gene in gene_desc_map:
                new_condition = gene_desc_map[gene]
                source_used = "ensembl_gene"

            if new_condition and new_condition != old_condition:
                # In revise_all mode: never downgrade a named condition to
                # a generic one (e.g. ClinVar disease → Ensembl gene desc).
                if revise_all and not _is_generic(old_condition) and _is_generic(new_condition):
                    continue
                if not dry_run:
                    # Merge: update condition in data dict, preserve everything else
                    updated_data = {**mapping.data, "condition": new_condition}
                    # Also update the primary dedup field if it had the old generic name
                    primary = _PRIMARY_FIELD.get(mapping.category, "condition")
                    if updated_data.get(primary) == old_condition:
                        updated_data[primary] = new_condition
                    mapping.data = updated_data

                stats["total_updated"] += 1
                stats["by_category"][mapping.category] = stats["by_category"].get(mapping.category, 0) + 1
                stats["by_source"][source_used] += 1

                if len(stats["examples"]) < 20:
                    stats["examples"].append({
                        "rsid": rsid, "gene": gene, "category": mapping.category,
                        "old": old_condition, "new": new_condition, "source": source_used,
                    })

        if not dry_run:
            await session.commit()

    return stats
