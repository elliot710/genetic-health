"""
Auto-categorization service — generates VariantMapping rows by running
CategoryRules against the ClinVar PostgreSQL tables.

Run via admin endpoint: POST /api/admin/auto-categorize
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func, text, and_, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session_factory
from ..db.models import (
    CategoryRule, ClinVarVariant, ClinVarGeneCondition,
    VariantMapping, GnomadVariant, GnomadGeneConstraint,
    SharedVariantAnnotation, GeneticMarker,
)
from .multi_source_categorizer import categorize_variant, CategorySuggestion, _SEVERE_EXCLUSION_KW

logger = logging.getLogger(__name__)

# Upper limit on auto-generated mappings per category to keep the table manageable
MAX_MAPPINGS_PER_CATEGORY = 500

# Categories where severe-condition exclusion applies
_LIFESTYLE_CATEGORIES = frozenset([
    "sports", "physical", "personality", "nutrition", "wellness",
    "methylation", "detox", "cognitive", "ancestry",
])

# Minimum review-status quality for auto-categorization.
# Variants with no-assertion / no-classification / single submitter
# without criteria are excluded regardless.
_REQUIRE_CRITERIA_REVIEW = True


class AutoCategorizer:
    """Runs CategoryRules against ClinVar data to generate VariantMapping rows."""

    async def run(self, *, categories: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run auto-categorization. Returns stats per category."""
        start = time.time()
        stats: Dict[str, Any] = {}

        async with async_session_factory() as session:
            # Load active rules
            q = select(CategoryRule).where(CategoryRule.is_active == True).order_by(
                CategoryRule.category, CategoryRule.priority
            )
            if categories:
                q = q.where(CategoryRule.category.in_(categories))

            result = await session.execute(q)
            rules = result.scalars().all()

            if not rules:
                return {"error": "No active category rules found. Seed rules first."}

            # Group rules by category
            rules_by_cat: Dict[str, List[CategoryRule]] = {}
            for rule in rules:
                rules_by_cat.setdefault(rule.category, []).append(rule)

            logger.info("Auto-categorizer: %d rules across %d categories",
                        len(rules), len(rules_by_cat))

            for category, cat_rules in rules_by_cat.items():
                n = await self._process_category(session, category, cat_rules)
                stats[category] = n
                logger.info("  %s: %d new mappings", category, n)

            await session.commit()

        # ── Phase 2: Multi-source annotation pass ───────────────────
        # Process shared_variant_annotations through the multi-source engine
        annotation_stats = await self._run_annotation_pass(categories=categories)
        stats["annotation_pass"] = annotation_stats

        stats["total_elapsed_s"] = round(time.time() - start, 1)
        stats["total_new_mappings"] = sum(
            v for k, v in stats.items()
            if k not in ("total_elapsed_s", "total_new_mappings", "annotation_pass")
        ) + annotation_stats.get("total_new", 0)
        return stats

    async def _run_annotation_pass(
        self,
        *,
        categories: Optional[List[str]] = None,
        batch_size: int = 5000,
        min_confidence: float = 0.4,
    ) -> Dict[str, Any]:
        """Process shared_variant_annotations through multi-source categorizer.

        Reads annotation JSON columns and uses the multi-source engine to
        create high-confidence mappings. Only processes variants that don't
        already have an active mapping in a given category.
        """
        stats = {"processed": 0, "total_new": 0, "by_category": {}}

        # Pre-load condition hints from all DB sources for better naming
        from .multi_source_categorizer import load_condition_hints
        from ..db.models import EnsemblGene
        # Load all gene symbols that have descriptions (for condition naming)
        async with async_session_factory() as hints_session:
            result = await hints_session.execute(
                select(EnsemblGene.gene_symbol).distinct()
            )
            all_genes = [r[0] for r in result.all()]
        condition_hints = await load_condition_hints(all_genes)
        logger.info("Loaded condition hints: %d gene conditions, %d gene descriptions",
                     len(condition_hints.get("gene_conditions", {})),
                     len(condition_hints.get("gene_descriptions", {})))

        async with async_session_factory() as session:
            # Count total annotations to process
            count_q = select(func.count(SharedVariantAnnotation.id)).where(
                SharedVariantAnnotation.clinvar_local_data.isnot(None),
            )
            total = (await session.execute(count_q)).scalar() or 0
            logger.info("Annotation pass: %d annotations with ClinVar local data", total)

            offset = 0
            while offset < total:
                rows = (await session.execute(
                    select(
                        SharedVariantAnnotation.rsid,
                        SharedVariantAnnotation.clinvar_local_data,
                        SharedVariantAnnotation.clinvar_data,
                        SharedVariantAnnotation.ensembl_data,
                        SharedVariantAnnotation.alpha_missense_data,
                        SharedVariantAnnotation.gnomad_data,
                        SharedVariantAnnotation.snpedia_data,
                        SharedVariantAnnotation.thousand_genomes_data,
                        SharedVariantAnnotation.gnomad_tx_data,
                    )
                    .where(SharedVariantAnnotation.clinvar_local_data.isnot(None))
                    .order_by(SharedVariantAnnotation.id)
                    .offset(offset)
                    .limit(batch_size)
                )).all()

                if not rows:
                    break

                for row in rows:
                    rsid = row[0]
                    annotations = {
                        "clinvar_local_data": row[1],
                        "clinvar_data": row[2],
                        "ensembl_data": row[3],
                        "alpha_missense_data": row[4],
                        "gnomad_data": row[5],
                        "snpedia_data": row[6],
                        "thousand_genomes_data": row[7],
                        "gnomad_tx_data": row[8],
                    }

                    suggestions = categorize_variant(rsid, annotations,
                                                      condition_hints=condition_hints)
                    for s in suggestions:
                        if s.confidence < min_confidence:
                            continue
                        if categories and s.category not in categories:
                            continue

                        # Check if we've hit the per-category cap
                        cat_count = stats["by_category"].get(s.category, 0)
                        if cat_count >= MAX_MAPPINGS_PER_CATEGORY:
                            continue

                        # Upsert: insert or update only when new confidence is
                        # higher (prevents downgrades from re-runs with fewer
                        # annotation sources).
                        stmt = insert(VariantMapping).values(
                            category=s.category,
                            map_type="rsid",
                            key=rsid,
                            data=s.data,
                            sources=s.sources,
                            confidence=s.confidence,
                            is_active=True,
                            is_auto_discovered=True,
                        ).on_conflict_do_update(
                            index_elements=["category", "map_type", "key"],
                            set_={
                                "data": s.data,
                                "sources": s.sources,
                                "confidence": s.confidence,
                                "is_active": True,
                            },
                            where=VariantMapping.confidence < s.confidence,
                        )
                        result = await session.execute(stmt)
                        if result.rowcount > 0:
                            stats["total_new"] += 1
                            stats["by_category"][s.category] = cat_count + 1

                stats["processed"] += len(rows)
                offset += batch_size
                if offset % 20000 == 0:
                    logger.info("  Annotation pass: %d/%d processed, %d new mappings",
                                offset, total, stats["total_new"])

            await session.commit()

        logger.info("Annotation pass complete: %d processed, %d new mappings",
                    stats["processed"], stats["total_new"])
        return stats

    async def _process_category(
        self,
        session: AsyncSession,
        category: str,
        rules: List[CategoryRule],
    ) -> int:
        """Process all rules for one category. Returns count of new mappings."""
        # Collect candidate (rsid, map_type, data) tuples from all rules
        candidates: Dict[str, dict] = {}  # key → {map_type, data}

        for rule in rules:
            matches = await self._evaluate_rule(session, category, rule)
            for key, entry in matches.items():
                if key not in candidates:
                    candidates[key] = entry

                if len(candidates) >= MAX_MAPPINGS_PER_CATEGORY:
                    break  # This rule filled the quota
            # Don't break the outer loop — let remaining rules contribute
            # new keys up to the cap
            if len(candidates) >= MAX_MAPPINGS_PER_CATEGORY:
                break

        if not candidates:
            return 0

        # Upsert into variant_mappings
        inserted = 0
        for key, entry in candidates.items():
            source_name = entry["data"].get("source", "clinvar_auto")
            stmt = insert(VariantMapping).values(
                category=category,
                map_type=entry["map_type"],
                key=key,
                data=entry["data"],
                sources=[source_name],
                confidence=0.3,  # Single-source ClinVar rule = baseline confidence
                is_active=True,
                is_auto_discovered=True,
            ).on_conflict_do_nothing(
                index_elements=["category", "map_type", "key"]
            )
            result = await session.execute(stmt)
            if result.rowcount > 0:
                inserted += 1

        return inserted

    async def _evaluate_rule(
        self,
        session: AsyncSession,
        category: str,
        rule: CategoryRule,
    ) -> Dict[str, dict]:
        """Evaluate a single rule, return matching {key: {map_type, data}}."""
        rt = rule.rule_type
        rv = rule.rule_value
        template = rule.mapping_data_template or {}

        if rt == "clinvar_significance":
            return await self._match_significance(session, category, rv, template)
        elif rt == "clinvar_condition_keyword":
            return await self._match_condition_keyword(session, category, rv, template)
        elif rt == "gene_list":
            return await self._match_gene_list(session, category, rv, template)
        elif rt == "molecular_consequence":
            return await self._match_molecular_consequence(session, category, rv, template)
        elif rt == "origin":
            return await self._match_origin(session, category, rv, template)
        elif rt == "gnomad_rare_variant":
            return await self._match_gnomad_rare(session, category, rv, template)
        elif rt == "gnomad_constrained_gene":
            return await self._match_gnomad_constrained(session, category, rv, template)
        else:
            logger.warning("Unknown rule type: %s", rt)
            return {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_severe_for_category(condition: str, category: str) -> bool:
        """Return True if condition describes a severe medical condition that
        should NOT be placed in a lifestyle/trait panel."""
        if category not in _LIFESTYLE_CATEGORIES:
            return False
        cond_lower = condition.lower()
        return any(kw in cond_lower for kw in _SEVERE_EXCLUSION_KW)

    @staticmethod
    def _populate_category_fields(data: dict, category: str, condition: str, gene: str):
        """Populate dedup-critical fields with category-appropriate values.

        FLAW-01 fix: instead of blindly setting all fields (trait, domain, metric,
        nutrient, category) to the disease name, set only the semantically
        relevant field to the condition and the rest to category-aware labels.
        Each generator uses a specific dedup_field — only that field needs the
        condition-level granularity. Others just need a non-empty value.
        """
        from .multi_source_categorizer import _category_aware_label

        # Category → primary dedup field mapping (what the generator uses)
        _PRIMARY_FIELD = {
            'health': 'condition',
            'carrier': 'condition',
            'drug_response': 'drug',
            'nutrition': 'nutrient',
            'sports': 'category',
            'wellness': 'metric',
            'cognitive': 'domain',
            'personality': 'trait',
            'physical_traits': 'trait',
            'methylation': 'gene',
            'detox': 'gene',
            'rare': 'condition',
            'uncommon': 'condition',
        }

        primary = _PRIMARY_FIELD.get(category, 'condition')

        # Set the primary field to the condition (meaningful dedup key)
        data.setdefault(primary, condition)

        # Set remaining fields to category-aware labels that make semantic
        # sense (e.g. "MTHFR metabolism" for nutrition instead of "MTHFR variant")
        for field in ('condition', 'trait', 'domain', 'metric', 'nutrient', 'category'):
            if field != primary:
                fallback = _category_aware_label(gene, category, field) if gene else condition
                data.setdefault(field, fallback)

    @staticmethod
    def _clean_condition(raw: str) -> str:
        """Extract the first meaningful condition name from a raw ClinVar conditions string.
        
        Returns empty string for garbage entries so callers can skip them.
        """
        if not raw:
            return ""
        # BUG-02: Reject entire-string garbage values, not just when embedded in pipes
        _GARBAGE = {
            'not provided', 'not specified', 'see cases', 'not applicable',
            'none', 'unknown', '-', '.', '',
        }
        if raw.strip().lower() in _GARBAGE:
            return ""
        if '|' not in raw and ';' not in raw:
            return raw.strip()
        parts = raw.replace(';', '|').split('|')
        for part in parts:
            cleaned = part.strip()
            if cleaned and cleaned.lower() not in _GARBAGE:
                if cleaned.isupper():
                    cleaned = cleaned.title()
                return cleaned
        return ""

    @staticmethod
    def _risk_multiplier_from_review_status(review_status: str, sig: str) -> float:
        """Map ClinVar review star level to risk_multiplier.

        BUG-02 fix: replaces uniform 3.0 for all Pathogenic variants with
        evidence-strength-calibrated values based on ClinVar star level.
          0-stars (single submitter, no criteria) → filtered out upstream
          1-star  (criteria provided, single submitter)       → 1.2
          2-stars (criteria provided, multiple submitters)    → 1.5
          3-stars (reviewed by expert panel)                  → 2.0
          4-stars (practice guideline)                        → 3.0
        Likely pathogenic gets 80% of the pathogenic value at each tier.
        """
        rs = (review_status or '').lower()
        is_likely = 'likely' in (sig or '').lower().replace('_', ' ')

        if 'practice guideline' in rs:
            mult = 3.0
        elif 'expert panel' in rs:
            mult = 2.0
        elif 'multiple submitters' in rs or 'no conflicts' in rs:
            mult = 1.5
        else:
            # Single submitter with criteria or other
            mult = 1.2

        return round(mult * 0.8 if is_likely else mult, 2)

    # ------------------------------------------------------------------
    # Rule matchers
    # ------------------------------------------------------------------

    async def _match_significance(
        self, session: AsyncSession, category: str, sig_pattern: str, template: dict
    ) -> Dict[str, dict]:
        """Match ClinVar variants by clinical_significance (case-insensitive ILIKE).

        BUG-02 fix: Also scales risk_multiplier per ClinVar review star level
        (1-star=1.2, 2-star=1.5, 3-star=2.0, 4-star=3.0) instead of uniform 3.0.
        Requires minimum review quality and filters garbage condition names.
        """
        result = await session.execute(
            select(
                ClinVarVariant.rsid,
                ClinVarVariant.gene,
                ClinVarVariant.clinical_significance,
                ClinVarVariant.conditions,
                ClinVarVariant.review_status,
            )
            .where(ClinVarVariant.clinical_significance.ilike(f"%{sig_pattern}%"))
            .where(ClinVarVariant.rsid.isnot(None))
            .where(~ClinVarVariant.clinical_significance.ilike('benign%'))
            .where(~ClinVarVariant.clinical_significance.ilike('likely_benign%'))
            .where(~ClinVarVariant.clinical_significance.ilike('likely benign%'))
            .where(~ClinVarVariant.clinical_significance.ilike('conflicting%'))
            .where(~ClinVarVariant.clinical_significance.ilike('drug%response%'))
            .where(ClinVarVariant.review_status.isnot(None))
            .where(~ClinVarVariant.review_status.ilike('no assertion%'))
            .where(~ClinVarVariant.review_status.ilike('no_assertion%'))
            .where(~ClinVarVariant.review_status.ilike('no classification%'))
            .where(~ClinVarVariant.review_status.ilike('no_classification%'))
            .where(ClinVarVariant.review_status != '-')
            .where(ClinVarVariant.review_status != '')
            .distinct(ClinVarVariant.rsid)
            .limit(MAX_MAPPINGS_PER_CATEGORY)
        )
        out: Dict[str, dict] = {}
        for row in result.all():
            rsid, gene, sig, cond, review = row
            cond = cond or f"{gene or 'Unknown'} variant"
            clean = self._clean_condition(cond)
            if not clean:
                continue
            if self._is_severe_for_category(clean, category):
                continue
            data = {**template}
            data.setdefault("condition", clean)
            data.setdefault("clinical_significance", sig)
            data.setdefault("gene", gene or "")
            data.setdefault("source", "clinvar_auto")
            data["review_status"] = review or ""
            # BUG-02: evidence-calibrated risk_multiplier based on star level
            data["risk_multiplier"] = self._risk_multiplier_from_review_status(review, sig)
            self._populate_category_fields(data, category, clean, gene or "")
            out[rsid] = {"map_type": "rsid", "data": data}
        return out

    async def _match_condition_keyword(
        self, session: AsyncSession, category: str, keyword: str, template: dict
    ) -> Dict[str, dict]:
        """Match ClinVar variants where conditions contain a keyword.

        BUG-02 fix: uses review-status-based risk_multiplier scaling and requires
        minimum review quality.
        """
        result = await session.execute(
            select(
                ClinVarVariant.rsid,
                ClinVarVariant.gene,
                ClinVarVariant.clinical_significance,
                ClinVarVariant.conditions,
                ClinVarVariant.review_status,
            )
            .where(ClinVarVariant.conditions.ilike(f"%{keyword}%"))
            .where(ClinVarVariant.rsid.isnot(None))
            .where(~ClinVarVariant.clinical_significance.ilike('benign%'))
            .where(~ClinVarVariant.clinical_significance.ilike('likely_benign%'))
            .where(~ClinVarVariant.clinical_significance.ilike('likely benign%'))
            .where(ClinVarVariant.review_status.isnot(None))
            .where(~ClinVarVariant.review_status.ilike('no assertion%'))
            .where(~ClinVarVariant.review_status.ilike('no_assertion%'))
            .where(~ClinVarVariant.review_status.ilike('no classification%'))
            .where(~ClinVarVariant.review_status.ilike('no_classification%'))
            .where(ClinVarVariant.review_status != '-')
            .where(ClinVarVariant.review_status != '')
            .distinct(ClinVarVariant.rsid)
            .limit(MAX_MAPPINGS_PER_CATEGORY)
        )
        out: Dict[str, dict] = {}
        for row in result.all():
            rsid, gene, sig, cond, review = row
            cond = cond or keyword
            clean = self._clean_condition(cond)
            if not clean:
                continue
            if self._is_severe_for_category(clean, category):
                continue
            data = {**template}
            data.setdefault("condition", clean)
            data.setdefault("clinical_significance", sig or "")
            data.setdefault("gene", gene or "")
            data.setdefault("source", "clinvar_auto")
            data["review_status"] = review or ""
            # BUG-02: evidence-calibrated multiplier; VUS/conflicting capped lower
            sig_lower = (sig or '').lower()
            if 'uncertain' in sig_lower or 'conflicting' in sig_lower:
                data["risk_multiplier"] = min(
                    self._risk_multiplier_from_review_status(review, sig), 1.3
                )
            else:
                data["risk_multiplier"] = self._risk_multiplier_from_review_status(review, sig)
            self._populate_category_fields(data, category, clean, gene or "")
            out[rsid] = {"map_type": "rsid", "data": data}
        return out

    async def _match_gene_list(
        self, session: AsyncSession, category: str, genes_csv: str, template: dict
    ) -> Dict[str, dict]:
        """Match ClinVar variants by gene symbol (comma-separated list in rule_value).
        Creates gene-type mappings."""
        genes = [g.strip() for g in genes_csv.split(",") if g.strip()]
        if not genes:
            return {}

        # Query for found genes AND their most common non-garbage condition
        _GARBAGE_CONDS = ("not provided", "not specified", "see cases", "not applicable", "none", ".", "-", "")
        result = await session.execute(
            select(ClinVarVariant.gene, ClinVarVariant.conditions)
            .where(ClinVarVariant.gene.in_(genes))
            .where(ClinVarVariant.conditions.isnot(None))
        )
        rows = result.all()

        # Build gene → best condition map
        gene_conditions: Dict[str, str] = {}
        found_genes: set = set()
        for gene_val, raw_conds in rows:
            found_genes.add(gene_val)
            if gene_val in gene_conditions:
                continue  # Already have a condition for this gene
            if raw_conds:
                clean = self._clean_condition(raw_conds)
                if clean:
                    gene_conditions[gene_val] = clean

        # Also include genes found without conditions
        result2 = await session.execute(
            select(ClinVarVariant.gene)
            .where(ClinVarVariant.gene.in_(genes))
            .distinct()
        )
        for (g,) in result2.all():
            found_genes.add(g)

        out: Dict[str, dict] = {}
        for gene in found_genes:
            data = {**template}
            data["gene"] = gene
            data.setdefault("source", "clinvar_auto")
            condition_label = gene_conditions.get(gene, f"{gene} variant")
            self._populate_category_fields(data, category, condition_label, gene)
            out[gene] = {"map_type": "gene", "data": data}
        return out

    async def _match_molecular_consequence(
        self, session: AsyncSession, category: str, consequence: str, template: dict
    ) -> Dict[str, dict]:
        """Match VCF-derived molecular consequence."""
        result = await session.execute(
            select(
                ClinVarVariant.rsid,
                ClinVarVariant.gene,
                ClinVarVariant.molecular_consequence,
                ClinVarVariant.conditions,
                ClinVarVariant.review_status,
                ClinVarVariant.clinical_significance,
            )
            .where(ClinVarVariant.molecular_consequence.ilike(f"%{consequence}%"))
            .where(ClinVarVariant.rsid.isnot(None))
            .where(~ClinVarVariant.clinical_significance.ilike('benign%'))
            .where(~ClinVarVariant.clinical_significance.ilike('likely_benign%'))
            .where(~ClinVarVariant.clinical_significance.ilike('likely benign%'))
            .where(ClinVarVariant.review_status.isnot(None))
            .where(~ClinVarVariant.review_status.ilike('no assertion%'))
            .where(~ClinVarVariant.review_status.ilike('no_assertion%'))
            .where(~ClinVarVariant.review_status.ilike('no classification%'))
            .where(~ClinVarVariant.review_status.ilike('no_classification%'))
            .where(ClinVarVariant.review_status != '-')
            .where(ClinVarVariant.review_status != '')
            .distinct(ClinVarVariant.rsid)
            .limit(MAX_MAPPINGS_PER_CATEGORY)
        )
        out: Dict[str, dict] = {}
        for row in result.all():
            rsid, gene, mc, cond_raw, review, sig = row
            cond = self._clean_condition(cond_raw or "") or f"{gene} - {consequence}"
            if self._is_severe_for_category(cond, category):
                continue
            data = {**template}
            data.setdefault("condition", cond)
            data.setdefault("gene", gene or "")
            data.setdefault("molecular_consequence", mc)
            data.setdefault("source", "clinvar_auto")
            data["review_status"] = review or ""
            data["risk_multiplier"] = self._risk_multiplier_from_review_status(review, sig)
            self._populate_category_fields(data, category, cond, gene or "")
            out[rsid] = {"map_type": "rsid", "data": data}
        return out

    async def _match_origin(
        self, session: AsyncSession, category: str, origin_val: str, template: dict
    ) -> Dict[str, dict]:
        """Match by ClinVar origin (germline, somatic, etc.)."""
        result = await session.execute(
            select(
                ClinVarVariant.rsid,
                ClinVarVariant.gene,
                ClinVarVariant.clinical_significance,
                ClinVarVariant.conditions,
                ClinVarVariant.review_status,
            )
            .where(ClinVarVariant.origin.ilike(f"%{origin_val}%"))
            .where(ClinVarVariant.rsid.isnot(None))
            .where(~ClinVarVariant.clinical_significance.ilike('benign%'))
            .where(~ClinVarVariant.clinical_significance.ilike('likely_benign%'))
            .where(~ClinVarVariant.clinical_significance.ilike('likely benign%'))
            .where(ClinVarVariant.review_status.isnot(None))
            .where(~ClinVarVariant.review_status.ilike('no assertion%'))
            .where(~ClinVarVariant.review_status.ilike('no_assertion%'))
            .where(~ClinVarVariant.review_status.ilike('no classification%'))
            .where(~ClinVarVariant.review_status.ilike('no_classification%'))
            .where(ClinVarVariant.review_status != '-')
            .where(ClinVarVariant.review_status != '')
            .distinct(ClinVarVariant.rsid)
            .limit(MAX_MAPPINGS_PER_CATEGORY)
        )
        out: Dict[str, dict] = {}
        for row in result.all():
            rsid, gene, sig, cond_raw, review = row
            cond = self._clean_condition(cond_raw or "") or "Unknown"
            if self._is_severe_for_category(cond, category):
                continue
            data = {**template}
            data.setdefault("condition", cond)
            data.setdefault("gene", gene or "")
            data.setdefault("source", "clinvar_auto")
            data["review_status"] = review or ""
            data["risk_multiplier"] = self._risk_multiplier_from_review_status(review, sig)
            self._populate_category_fields(data, category, cond, gene or "")
            out[rsid] = {"map_type": "rsid", "data": data}
        return out

    async def _match_gnomad_rare(
        self, session: AsyncSession, category: str, af_threshold_str: str, template: dict
    ) -> Dict[str, dict]:
        """Match gnomAD variants below an allele frequency threshold (rare variants).
        rule_value = max AF threshold, e.g. '0.001' for variants with AF < 0.1%."""
        try:
            af_threshold = float(af_threshold_str)
        except ValueError:
            logger.warning("Invalid AF threshold: %s", af_threshold_str)
            return {}

        result = await session.execute(
            select(
                GnomadVariant.rsid,
                GnomadVariant.gene,
                GnomadVariant.af,
                GnomadVariant.consequence,
                GnomadVariant.impact,
            )
            .where(GnomadVariant.af < af_threshold)
            .where(GnomadVariant.af > 0)
            .where(GnomadVariant.rsid.isnot(None))
            .where(GnomadVariant.gene.isnot(None))
            .distinct(GnomadVariant.rsid)
            .limit(MAX_MAPPINGS_PER_CATEGORY)
        )
        out: Dict[str, dict] = {}
        for row in result.all():
            rsid, gene, af, consequence, impact = row
            data = {**template}
            data.setdefault("gene", gene or "")
            data.setdefault("af", af)
            data.setdefault("consequence", consequence or "")
            data.setdefault("impact", impact or "")
            data.setdefault("source", "gnomad_auto")
            label = f"{gene} - {consequence or 'rare variant'} (AF={af:.6f})"
            data.setdefault("condition", label)
            # FLAW-01: populate category-appropriate dedup fields
            self._populate_category_fields(data, category, label, gene or "")
            out[rsid] = {"map_type": "rsid", "data": data}
        return out

    async def _match_gnomad_constrained(
        self, session: AsyncSession, category: str, constraint_csv: str, template: dict
    ) -> Dict[str, dict]:
        """Match gnomAD gene constraint data. rule_value = 'pli:0.9' or 'loeuf:0.35'.
        Format: metric:threshold — genes with metric >= threshold (for pli) or <= threshold (for loeuf)."""
        parts = constraint_csv.split(":")
        if len(parts) != 2:
            logger.warning("Invalid constraint format: %s (expected 'metric:threshold')", constraint_csv)
            return {}

        metric, threshold_str = parts[0].strip(), parts[1].strip()
        try:
            threshold = float(threshold_str)
        except ValueError:
            logger.warning("Invalid threshold: %s", threshold_str)
            return {}

        if metric == "pli":
            condition = GnomadGeneConstraint.pli >= threshold
        elif metric == "loeuf":
            condition = GnomadGeneConstraint.loeuf <= threshold
        elif metric == "mis_z":
            condition = GnomadGeneConstraint.mis_z >= threshold
        else:
            logger.warning("Unknown constraint metric: %s", metric)
            return {}

        result = await session.execute(
            select(
                GnomadGeneConstraint.gene,
                GnomadGeneConstraint.pli,
                GnomadGeneConstraint.loeuf,
                GnomadGeneConstraint.mis_z,
            )
            .where(condition)
            .limit(MAX_MAPPINGS_PER_CATEGORY)
        )
        out: Dict[str, dict] = {}
        for row in result.all():
            gene, pli, loeuf, mis_z = row
            data = {**template}
            data["gene"] = gene
            data.setdefault("pli", pli)
            data.setdefault("loeuf", loeuf)
            data.setdefault("mis_z", mis_z)
            data.setdefault("source", "gnomad_auto")
            # Use tuple indexing — row is a result tuple, not an ORM object
            _metric_idx = {'pli': 1, 'loeuf': 2, 'mis_z': 3}
            metric_val = row[_metric_idx.get(metric, 1)]
            label = f"{gene} (constrained: {metric}={metric_val:.2f})" if isinstance(metric_val, (int, float)) else f"{gene} (constrained: {metric}={metric_val})"
            # FLAW-01: populate category-appropriate dedup fields
            self._populate_category_fields(data, category, label, gene)
            out[gene] = {"map_type": "gene", "data": data}
        return out


# ------------------------------------------------------------------
# Default category rules — seeded once
# ------------------------------------------------------------------

DEFAULT_CATEGORY_RULES: List[dict] = [
    # ===================================================================
    # HEALTH — dedup_field='condition'
    # from_rsid needs: condition(matcher), risk_multiplier
    # from_gene needs: condition, risk_level, risk_score, recommendations
    # ===================================================================
    {"category": "health", "rule_type": "clinvar_significance", "rule_value": "Pathogenic",
     "priority": 10, "mapping_data_template": {"risk_level": "high", "risk_score": "3.0x", "risk_multiplier": 3.0,
                                                "recommendations": ["Consult genetic counselor", "Regular screening recommended"]}},
    {"category": "health", "rule_type": "clinvar_significance", "rule_value": "Likely_pathogenic",
     "priority": 20, "mapping_data_template": {"risk_level": "moderate", "risk_score": "2.0x", "risk_multiplier": 2.0,
                                                "recommendations": ["Discuss with healthcare provider", "Consider additional testing"]}},
    {"category": "health", "rule_type": "clinvar_condition_keyword", "rule_value": "cancer",
     "priority": 30, "mapping_data_template": {"risk_level": "high", "risk_score": "2.5x", "risk_multiplier": 2.5,
                                                "recommendations": ["Cancer risk screening", "Genetic counseling recommended"]}},
    {"category": "health", "rule_type": "clinvar_condition_keyword", "rule_value": "cardiomyopathy",
     "priority": 30, "mapping_data_template": {"risk_level": "high", "risk_score": "2.5x", "risk_multiplier": 2.5,
                                                "recommendations": ["Cardiology evaluation", "Echocardiogram recommended"]}},
    {"category": "health", "rule_type": "clinvar_condition_keyword", "rule_value": "diabetes",
     "priority": 40, "mapping_data_template": {"risk_level": "moderate", "risk_score": "1.5x", "risk_multiplier": 1.5,
                                                "recommendations": ["Monitor blood glucose", "Healthy diet and exercise"]}},
    {"category": "health", "rule_type": "clinvar_condition_keyword", "rule_value": "Alzheimer",
     "priority": 40, "mapping_data_template": {"risk_level": "moderate", "risk_score": "2.0x", "risk_multiplier": 2.0,
                                                "recommendations": ["Cognitive health monitoring", "Brain-healthy lifestyle"]}},

    # ===================================================================
    # DRUG RESPONSES — custom generator
    # gene_map needs: gene(matcher), drugs (list of [drug_name, response, recommendation])
    # rsid_map needs: gene(matcher), drugs (list of drug name strings)
    # ===================================================================
    {"category": "drug", "rule_type": "gene_list",
     "rule_value": "CYP2D6,CYP2C19,CYP2C9,CYP3A4,CYP3A5,CYP1A2,CYP2B6,DPYD,TPMT,UGT1A1,NUDT15,SLCO1B1,VKORC1,NAT2,ABCB1,CYP2A6,CYP4F2,G6PD,IFNL3,RYR1",
     "priority": 10, "mapping_data_template": {"drugs": [["Substrate medications", "variable", "Pharmacogenomic testing recommended for dosage adjustments"]]}},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "drug response",
     "priority": 30, "mapping_data_template": {"drugs": ["Associated medication"]}},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "pharmacokinetic",
     "priority": 30, "mapping_data_template": {"drugs": ["Associated medication"]}},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "drug metabolism",
     "priority": 30, "mapping_data_template": {"drugs": ["Associated medication"]}},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "drug sensitivity",
     "priority": 30, "mapping_data_template": {"drugs": ["Associated medication"]}},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "warfarin",
     "priority": 20, "mapping_data_template": {"drugs": ["Warfarin"]}},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "statin",
     "priority": 20, "mapping_data_template": {"drugs": ["Statins"]}},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "metformin",
     "priority": 20, "mapping_data_template": {"drugs": ["Metformin"]}},

    # ===================================================================
    # PHYSICAL TRAITS — dedup_field='trait'
    # from_rsid needs: trait(matcher), category, result, confidence
    # from_gene needs: trait(matcher), category, result, confidence, description
    # ===================================================================
    {"category": "physical", "rule_type": "gene_list",
     "rule_value": "MC1R,OCA2,HERC2,IRF4,SLC24A5,SLC45A2,KITLG,TYRP1,TYR,ASIP,BNC2,EDAR",
     "priority": 20, "mapping_data_template": {"category": "appearance", "result": "Variant detected", "confidence": "high",
                                                "description": "Gene associated with physical trait variation"}},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "hair",
     "priority": 30, "mapping_data_template": {"category": "appearance", "result": "Variant detected", "confidence": "moderate"}},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "eye color",
     "priority": 30, "mapping_data_template": {"category": "appearance", "result": "Variant detected", "confidence": "moderate"}},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "skin",
     "priority": 30, "mapping_data_template": {"category": "appearance", "result": "Variant detected", "confidence": "moderate"}},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "height",
     "priority": 30, "mapping_data_template": {"category": "anthropometric", "result": "Variant detected", "confidence": "moderate"}},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "pigment",
     "priority": 30, "mapping_data_template": {"category": "appearance", "result": "Variant detected", "confidence": "moderate"}},

    # ===================================================================
    # NUTRITION — dedup_field='nutrient'
    # from_rsid/gene needs: nutrient(matcher), metabolism, recommendations, sensitivity
    # ===================================================================
    {"category": "nutrition", "rule_type": "gene_list",
     "rule_value": "MTHFR,FUT2,LCT,MCM6,FADS1,FADS2,BCMO1,SLC23A1,GC,CYP2R1,VDR,TCN1,TCN2,NBPF3,HFE,TF,TMPRSS6,SLC30A8",
     "priority": 10, "mapping_data_template": {"metabolism": "variable", "recommendations": ["Consider testing nutrient levels"],
                                                "sensitivity": "moderate"}},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "lactose",
     "priority": 30, "mapping_data_template": {"nutrient": "Lactose", "metabolism": "intolerant",
                                                "recommendations": ["Avoid dairy or use lactase supplements"], "sensitivity": "high"}},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "celiac",
     "priority": 30, "mapping_data_template": {"nutrient": "Gluten", "metabolism": "intolerant",
                                                "recommendations": ["Strict gluten-free diet"], "sensitivity": "high"}},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "vitamin D",
     "priority": 30, "mapping_data_template": {"nutrient": "Vitamin D", "metabolism": "variable",
                                                "recommendations": ["Monitor vitamin D levels", "Consider supplementation"], "sensitivity": "moderate"}},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "iron",
     "priority": 30, "mapping_data_template": {"nutrient": "Iron", "metabolism": "variable",
                                                "recommendations": ["Monitor iron levels"], "sensitivity": "moderate"}},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "folate",
     "priority": 30, "mapping_data_template": {"nutrient": "Folate", "metabolism": "variable",
                                                "recommendations": ["Consider methylfolate supplementation"], "sensitivity": "moderate"}},

    # ===================================================================
    # SPORTS / PERFORMANCE — dedup_field='category'
    # from_rsid/gene needs: category(matcher), advantage, recommendations, advice
    # ===================================================================
    {"category": "sports", "rule_type": "gene_list",
     "rule_value": "ACTN3,ACE,PPARGC1A,PPARA,ADRB2,ADRB3,NOS3,VEGFA,HIF1A,EPAS1,AMPD1,CKM,BDNF,IL6,TNF,COL1A1,COL5A1,GDF5,MMP3",
     "priority": 10, "mapping_data_template": {"advantage": "Genetic variant associated with athletic performance",
                                                "recommendations": ["Tailored training program recommended"],
                                                "advice": "Consult sports medicine specialist for personalized program"}},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "muscle",
     "priority": 30, "mapping_data_template": {"advantage": "Muscle-related genetic variant",
                                                "recommendations": ["Strength assessment recommended"],
                                                "advice": "Consider consulting exercise physiologist"}},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "myopathy",
     "priority": 30, "mapping_data_template": {"advantage": "Variant affecting muscle function",
                                                "recommendations": ["Medical evaluation before intense exercise"],
                                                "advice": "Work with a specialist for safe exercise programming"}},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "exercise intolerance",
     "priority": 30, "mapping_data_template": {"advantage": "Exercise tolerance variant detected",
                                                "recommendations": ["Gradual exercise progression"],
                                                "advice": "Medical clearance recommended before starting exercise program"}},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "rhabdomyolysis",
     "priority": 20, "mapping_data_template": {"advantage": "Rhabdomyolysis risk variant",
                                                "recommendations": ["Avoid extreme exertion", "Stay well-hydrated"],
                                                "advice": "Medical supervision recommended for high-intensity training"}},

    # ===================================================================
    # COGNITIVE — dedup_field='domain'
    # from_rsid/gene needs: domain(matcher), score, percentile, suggestions
    # ===================================================================
    {"category": "cognitive", "rule_type": "gene_list",
     "rule_value": "COMT,BDNF,DRD2,DRD4,KIBRA,APOE,CHRNA4,NRXN1,DISC1,NRG1,DTNBP1,AKT1",
     "priority": 10, "mapping_data_template": {"score": "variable", "percentile": 50,
                                                "suggestions": ["Cognitive enrichment activities", "Brain-healthy lifestyle"]}},
    {"category": "cognitive", "rule_type": "clinvar_condition_keyword", "rule_value": "intellectual disability",
     "priority": 30, "mapping_data_template": {"score": "reduced", "percentile": 30,
                                                "suggestions": ["Professional cognitive assessment recommended"]}},
    {"category": "cognitive", "rule_type": "clinvar_condition_keyword", "rule_value": "memory",
     "priority": 30, "mapping_data_template": {"score": "variable", "percentile": 50,
                                                "suggestions": ["Memory exercises", "Cognitive training programs"]}},
    {"category": "cognitive", "rule_type": "clinvar_condition_keyword", "rule_value": "learning disability",
     "priority": 30, "mapping_data_template": {"score": "variable", "percentile": 40,
                                                "suggestions": ["Educational assessment recommended", "Adaptive learning strategies"]}},
    {"category": "cognitive", "rule_type": "clinvar_condition_keyword", "rule_value": "neurodegenerat",
     "priority": 30, "mapping_data_template": {"score": "variable", "percentile": 45,
                                                "suggestions": ["Cognitive monitoring", "Neuroprotective lifestyle habits"]}},

    # ===================================================================
    # PERSONALITY / BEHAVIOR — dedup_field='trait'
    # from_rsid/gene needs: trait(matcher), tendency, confidence, insights
    # ===================================================================
    {"category": "personality", "rule_type": "gene_list",
     "rule_value": "SLC6A4,DRD4,DRD2,MAOA,COMT,OXTR,AVPR1A,HTR2A,FKBP5,CRHR1,TPH2",
     "priority": 10, "mapping_data_template": {"tendency": "variable", "confidence": "moderate",
                                                "insights": ["Genetic variation may influence behavioral tendencies"]}},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "anxiety",
     "priority": 30, "mapping_data_template": {"tendency": "variable", "confidence": "low",
                                                "insights": ["Genetic variant associated with anxiety-related traits"]}},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "depression",
     "priority": 30, "mapping_data_template": {"tendency": "variable", "confidence": "low",
                                                "insights": ["Genetic variant associated with mood regulation"]}},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "behavior",
     "priority": 30, "mapping_data_template": {"tendency": "variable", "confidence": "low",
                                                "insights": ["Genetic variant associated with behavioral phenotype"]}},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "autism",
     "priority": 30, "mapping_data_template": {"tendency": "variable", "confidence": "low",
                                                "insights": ["Genetic variant associated with neurodevelopmental traits"]}},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "schizophrenia",
     "priority": 30, "mapping_data_template": {"tendency": "variable", "confidence": "low",
                                                "insights": ["Genetic variant associated with neuropsychiatric traits"]}},

    # ===================================================================
    # CARRIER STATUS — custom generator
    # needs: condition(matcher), status
    # ===================================================================
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "cystic fibrosis",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "autosomal_recessive"}},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "sickle cell",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "autosomal_recessive"}},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "thalassemia",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "autosomal_recessive"}},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "Tay-Sachs",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "autosomal_recessive"}},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "hemophilia",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "x_linked"}},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "Gaucher",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "autosomal_recessive"}},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "phenylketonuria",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "autosomal_recessive"}},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "Duchenne",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "x_linked"}},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "Wilson disease",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "autosomal_recessive"}},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "spinal muscular atrophy",
     "priority": 10, "mapping_data_template": {"status": "carrier", "inheritance_pattern": "autosomal_recessive"}},

    # ===================================================================
    # WELLNESS — dedup_field='metric'
    # from_rsid/gene needs: metric(matcher), predisposition, score, recommendations
    # ===================================================================
    {"category": "wellness", "rule_type": "gene_list",
     "rule_value": "CLOCK,PER2,PER3,CRY1,ADORA2A,ADA,DEC2,BHLHE41,NR1D1,TNF,IL6,IL10,CRP,LEPR,FTO,MC4R",
     "priority": 10, "mapping_data_template": {"predisposition": "variable", "score": "50",
                                                "recommendations": ["Monitor wellness indicators", "Healthy lifestyle habits"]}},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "sleep",
     "priority": 30, "mapping_data_template": {"predisposition": "variable", "score": "50",
                                                "recommendations": ["Sleep hygiene optimization", "Consider sleep study"]}},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "obesity",
     "priority": 30, "mapping_data_template": {"predisposition": "elevated risk", "score": "40",
                                                "recommendations": ["Regular physical activity", "Balanced nutrition plan"]}},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "inflammation",
     "priority": 30, "mapping_data_template": {"predisposition": "variable", "score": "50",
                                                "recommendations": ["Anti-inflammatory diet", "Monitor inflammatory markers"]}},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "circadian",
     "priority": 30, "mapping_data_template": {"predisposition": "variable", "score": "50",
                                                "recommendations": ["Consistent sleep schedule", "Light exposure management"]}},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "fatigue",
     "priority": 30, "mapping_data_template": {"predisposition": "variable", "score": "45",
                                                "recommendations": ["Energy management strategies", "Evaluate underlying causes"]}},

    # ===================================================================
    # METHYLATION — dedup_field='gene'
    # from_rsid/gene needs: gene(matcher), capacity, supplements
    # ===================================================================
    {"category": "methylation", "rule_type": "gene_list",
     "rule_value": "MTHFR,MTR,MTRR,COMT,CBS,BHMT,MAT1A,AHCY,SHMT1,SHMT2,FOLR1,FOLR2,DHFR,TYMS,TCN2,MTHFD1",
     "priority": 10, "mapping_data_template": {"capacity": "variable",
                                                "supplements": ["Consider methylfolate", "Monitor B12 levels"]}},
    {"category": "methylation", "rule_type": "clinvar_condition_keyword", "rule_value": "methylation",
     "priority": 30, "mapping_data_template": {"capacity": "reduced",
                                                "supplements": ["Methylfolate supplementation", "B12 monitoring"]}},
    {"category": "methylation", "rule_type": "clinvar_condition_keyword", "rule_value": "folate",
     "priority": 30, "mapping_data_template": {"capacity": "reduced",
                                                "supplements": ["Methylfolate", "Folinic acid consideration"]}},
    {"category": "methylation", "rule_type": "clinvar_condition_keyword", "rule_value": "homocysteine",
     "priority": 30, "mapping_data_template": {"capacity": "reduced",
                                                "supplements": ["B6, B12, and folate supplementation", "Homocysteine monitoring"]}},
    {"category": "methylation", "rule_type": "clinvar_condition_keyword", "rule_value": "neural tube",
     "priority": 30, "mapping_data_template": {"capacity": "reduced",
                                                "supplements": ["Adequate folate critical", "Prenatal supplementation"]}},

    # ===================================================================
    # DETOXIFICATION — dedup_field='gene'
    # from_rsid/gene needs: gene(matcher), phase, capacity, sensitivity, recommendations
    # ===================================================================
    {"category": "detox", "rule_type": "gene_list",
     "rule_value": "CYP1A1,CYP1A2,CYP1B1,CYP2E1,CYP2A6,GSTM1,GSTT1,GSTP1,NAT1,NAT2,NQO1,EPHX1,SOD2,CAT,GPX1,PON1,ALDH2",
     "priority": 10, "mapping_data_template": {"phase": "variable", "capacity": "variable",
                                                "sensitivity": "moderate",
                                                "recommendations": ["Support detoxification pathways"]}},
    {"category": "detox", "rule_type": "clinvar_condition_keyword", "rule_value": "glutathione",
     "priority": 30, "mapping_data_template": {"phase": "phase2", "capacity": "variable",
                                                "sensitivity": "moderate",
                                                "recommendations": ["Support glutathione levels", "Cruciferous vegetables"]}},
    {"category": "detox", "rule_type": "clinvar_condition_keyword", "rule_value": "oxidative stress",
     "priority": 30, "mapping_data_template": {"phase": "antioxidant", "capacity": "variable",
                                                "sensitivity": "elevated",
                                                "recommendations": ["Antioxidant-rich diet", "Minimize toxin exposure"]}},
    {"category": "detox", "rule_type": "clinvar_condition_keyword", "rule_value": "acetylation",
     "priority": 30, "mapping_data_template": {"phase": "phase2", "capacity": "variable",
                                                "sensitivity": "moderate",
                                                "recommendations": ["Monitor for drug acetylation effects"]}},
    {"category": "detox", "rule_type": "clinvar_condition_keyword", "rule_value": "chemical sensitivity",
     "priority": 30, "mapping_data_template": {"phase": "variable", "capacity": "reduced",
                                                "sensitivity": "elevated",
                                                "recommendations": ["Minimize chemical exposures", "Air purification"]}},

    # ===================================================================
    # ANCESTRY — hard-coded generator, maps not used. Kept for potential future use.
    # ===================================================================
    {"category": "ancestry", "rule_type": "gene_list",
     "rule_value": "SLC24A5,SLC45A2,HERC2,OCA2,MC1R,EDAR,ABCC11,LCT,ALDH2,ADH1B",
     "priority": 30, "mapping_data_template": {"population": "various", "confidence": "low"}},

    # ===================================================================
    # gnomAD-based rules — rare variants and constrained genes
    # ===================================================================
    # Rare variants (AF < 0.1%) in health category
    {"category": "health", "rule_type": "gnomad_rare_variant", "rule_value": "0.001",
     "priority": 50, "mapping_data_template": {"risk_level": "review", "risk_score": "1.5x", "risk_multiplier": 1.5,
                                                "recommendations": ["Rare variant — review clinical significance", "Genetic counseling may be beneficial"]}},
    # Highly constrained genes (loss-of-function intolerant)
    {"category": "health", "rule_type": "gnomad_constrained_gene", "rule_value": "pli:0.9",
     "priority": 45, "mapping_data_template": {"risk_level": "moderate", "risk_score": "2.0x", "risk_multiplier": 2.0,
                                                "recommendations": ["Gene highly intolerant to loss-of-function", "Variants in this gene warrant careful evaluation"]}},
    # Constrained genes for drug response
    {"category": "drug", "rule_type": "gnomad_constrained_gene", "rule_value": "pli:0.9",
     "priority": 40, "mapping_data_template": {"drugs": [["Substrate medications", "variable", "Gene is highly constrained — dosing may need adjustment"]]}},
]


async def seed_category_rules(*, force: bool = False) -> Dict[str, int]:
    """Insert default category rules into the database.
    Returns count per category. If force=True, deletes all existing rules first."""
    async with async_session_factory() as session:
        if force:
            await session.execute(text("DELETE FROM category_rules"))

        existing = (await session.execute(
            select(func.count()).select_from(CategoryRule)
        )).scalar()

        if existing and not force:
            return {"skipped": existing, "message": "Rules already seeded. Use force=true to re-seed."}

        inserted = 0
        by_cat: Dict[str, int] = {}
        for rule_def in DEFAULT_CATEGORY_RULES:
            stmt = insert(CategoryRule).values(**rule_def).on_conflict_do_nothing()
            result = await session.execute(stmt)
            if result.rowcount > 0:
                inserted += 1
                cat = rule_def["category"]
                by_cat[cat] = by_cat.get(cat, 0) + 1

        await session.commit()

    logger.info("Seeded %d category rules across %d categories", inserted, len(by_cat))
    return {"inserted": inserted, "by_category": by_cat}
