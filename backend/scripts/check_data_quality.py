"""Quick check of ref_allele and genotype data quality."""
import asyncio
from backend.db.database import async_session_factory
from sqlalchemy import text


async def check():
    async with async_session_factory() as s:
        # Check how many markers have ref_allele set
        r = await s.execute(text(
            "SELECT COUNT(*) as total, "
            "COUNT(ref_allele) as has_ref, "
            "COUNT(CASE WHEN ref_allele IS NULL THEN 1 END) as null_ref, "
            "COUNT(CASE WHEN ref_allele IN ('', '-', '.', 'N') THEN 1 END) as invalid_ref "
            "FROM genetic_markers"
        ))
        row = r.fetchone()
        print(f"Total markers: {row[0]}")
        print(f"Has ref_allele: {row[1]}")
        print(f"NULL ref: {row[2]}")
        print(f"Invalid ref: {row[3]}")

        # Check genotype patterns in latest analysis
        r2 = await s.execute(text(
            "SELECT COUNT(*) as total, "
            "COUNT(genotype) as has_gt, "
            "COUNT(CASE WHEN genotype IS NULL THEN 1 END) as null_gt "
            "FROM analysis_variants "
            "WHERE analysis_id = (SELECT MAX(id) FROM genetic_analyses WHERE analysis_status = 'completed')"
        ))
        row2 = r2.fetchone()
        print(f"\nVariants (latest analysis):")
        print(f"Total: {row2[0]}, Has genotype: {row2[1]}, NULL genotype: {row2[2]}")

        # Sample genotypes with ref/alt
        r3 = await s.execute(text(
            "SELECT av.genotype, gm.ref_allele, gm.alt_alleles "
            "FROM analysis_variants av "
            "JOIN genetic_markers gm ON av.marker_id = gm.id "
            "WHERE av.analysis_id = (SELECT MAX(id) FROM genetic_analyses WHERE analysis_status = 'completed') "
            "AND av.genotype IS NOT NULL "
            "ORDER BY RANDOM() "
            "LIMIT 20"
        ))
        print("\nSample variants (genotype | ref | alt):")
        for row in r3.fetchall():
            print(f"  {str(row[0]):10s} | {str(row[1]):5s} | {str(row[2]):10s}")

        # Check how many variants match registry rsids
        r4 = await s.execute(text(
            "SELECT vm.category, COUNT(DISTINCT av.id) as matched_variants "
            "FROM variant_mappings vm "
            "JOIN analysis_variants av ON av.rsid = vm.key "
            "WHERE av.analysis_id = (SELECT MAX(id) FROM genetic_analyses WHERE analysis_status = 'completed') "
            "AND vm.map_type = 'rsid' AND vm.is_active = true "
            "GROUP BY vm.category ORDER BY matched_variants DESC"
        ))
        print("\nVariant mapping matches per category:")
        for row in r4.fetchall():
            print(f"  {row[0]:15s}: {row[1]} matched variants")

        # Check how many matched variants have ref_allele
        r5 = await s.execute(text(
            "SELECT COUNT(*) as total_matched, "
            "COUNT(gm.ref_allele) as has_ref, "
            "COUNT(CASE WHEN gm.ref_allele IS NULL THEN 1 END) as missing_ref "
            "FROM variant_mappings vm "
            "JOIN analysis_variants av ON av.rsid = vm.key "
            "JOIN genetic_markers gm ON av.marker_id = gm.id "
            "WHERE av.analysis_id = (SELECT MAX(id) FROM genetic_analyses WHERE analysis_status = 'completed') "
            "AND vm.map_type = 'rsid' AND vm.is_active = true"
        ))
        row5 = r5.fetchone()
        print(f"\nRegistry-matched variants ref_allele coverage:")
        print(f"  Total matched: {row5[0]}, Has ref: {row5[1]}, Missing ref: {row5[2]}")


asyncio.run(check())
