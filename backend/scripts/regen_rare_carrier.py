"""
Regenerate rare_mutations and carrier_status for analysis 69
using the updated generators that extract real data from annotations.

Usage (inside backend container):
  uv run python -m backend.scripts.regen_rare_carrier
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select, delete
from backend.db.database import async_session_factory
from backend.db.models import (
    GeneticAnalysis, AnalysisVariant, SharedVariantAnnotation,
    RareMutation, CarrierStatus
)
from backend.services.variant_types import AnnotationResult
from backend.services.insight_generators import GeneratorContext, generate_rare_mutations, generate_carrier_status


async def main():
    analysis_id = 69

    async with async_session_factory() as session:
        # 1. Delete old rows
        del_rare = await session.execute(
            delete(RareMutation).where(RareMutation.analysis_id == analysis_id)
        )
        del_carrier = await session.execute(
            delete(CarrierStatus).where(CarrierStatus.analysis_id == analysis_id)
        )
        print(f"Deleted {del_rare.rowcount} rare_mutations, {del_carrier.rowcount} carrier_status rows")

        # 2. Load variants for this analysis
        result = await session.execute(
            select(AnalysisVariant).where(AnalysisVariant.analysis_id == analysis_id)
        )
        variants = result.scalars().all()
        print(f"Loaded {len(variants)} variants")

        rsids = [v.rsid for v in variants if v.rsid]

        # 3. Load annotations in batches (asyncpg limit: 32767 params)
        annotations = []
        batch_size = 10000
        for i in range(0, len(rsids), batch_size):
            batch = rsids[i:i + batch_size]
            ann_result = await session.execute(
                select(SharedVariantAnnotation).where(SharedVariantAnnotation.rsid.in_(batch))
            )
            annotations.extend(ann_result.scalars().all())
        print(f"Loaded {len(annotations)} shared annotations")

        # 4. Build annotation_results dict matching what the generators expect
        annotation_results = {}
        for ann in annotations:
            merged = {'annotations': {}}
            if ann.ensembl_data:
                merged['annotations']['ensembl'] = ann.ensembl_data
            if ann.clinvar_data:
                merged['annotations']['clinvar'] = ann.clinvar_data
            if ann.clinvar_local_data:
                merged['annotations']['clinvar_local'] = ann.clinvar_local_data
            if ann.gnomad_data:
                merged['annotations']['gnomad'] = ann.gnomad_data

            annotation_results[ann.rsid] = AnnotationResult(
                rsid=ann.rsid,
                was_reused=True,
                annotation_data=merged,
                source='existing'
            )

        # 5. Run generators via GeneratorContext
        ctx = GeneratorContext(
            analysis_id=analysis_id,
            variants=variants,
            annotation_results=annotation_results,
            session=session,
            rsid_gene_map={},
            registry={},
        )

        rare_count = await generate_rare_mutations(ctx)
        carrier_count = await generate_carrier_status(ctx)

        await session.commit()
        print(f"Generated {rare_count} rare mutations, {carrier_count} carrier status records")


if __name__ == '__main__':
    asyncio.run(main())
