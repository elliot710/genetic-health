"""Re-run ancestry analysis for analysis_id=69 using updated algorithm."""
import asyncio
import sys
import os

sys.path.insert(0, '/app')
os.chdir('/app')


async def main():
    from backend.db.database import async_session_factory, engine
    from backend.db.models import AncestryResult, AnalysisVariant
    from sqlalchemy import select, delete
    from sqlalchemy.orm import joinedload

    from backend.services.insight_generators import GeneratorContext, generate_ancestry_results

    async with async_session_factory() as session:
        # Delete old ancestry results
        await session.execute(
            delete(AncestryResult).where(AncestryResult.analysis_id == 69)
        )
        await session.flush()
        print("Deleted old ancestry results")

        # Load variants for this analysis (with marker data)
        q = (
            select(AnalysisVariant)
            .options(joinedload(AnalysisVariant.marker))
            .where(AnalysisVariant.analysis_id == 69)
        )
        result = await session.execute(q)
        variants = result.scalars().unique().all()
        print(f"Loaded {len(variants)} variants")

        ctx = GeneratorContext(
            analysis_id=69,
            variants=variants,
            annotation_results={},
            session=session,
            rsid_gene_map={},
            registry={},
        )

        count = await generate_ancestry_results(ctx)
        await session.commit()
        print(f"Generated {count} ancestry result(s)")

        # Verify
        res = await session.execute(
            select(AncestryResult).where(AncestryResult.analysis_id == 69)
        )
        for r in res.scalars():
            print(f"Population: {r.population}")
            print(f"Percentage: {r.percentage}")
            print(f"Confidence: {r.confidence}")
            print(f"Composition: {r.composition}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
