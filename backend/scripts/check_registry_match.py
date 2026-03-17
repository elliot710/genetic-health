"""Check registry variant matching and alt_alleles data quality."""
import asyncio
from backend.db.database import async_session_factory
from sqlalchemy import text


async def check():
    async with async_session_factory() as s:
        # AnalysisVariant has no rsid column — rsid is on genetic_markers
        # Need to join through genetic_markers

        # Check how many variants match registry rsids
        r = await s.execute(text(
            "SELECT vm.category, COUNT(DISTINCT av.id) as matched "
            "FROM variant_mappings vm "
            "JOIN genetic_markers gm ON gm.rsid = vm.key "
            "JOIN analysis_variants av ON av.marker_id = gm.id "
            "WHERE av.analysis_id = (SELECT MAX(id) FROM genetic_analyses WHERE analysis_status = 'completed') "
            "AND vm.map_type = 'rsid' AND vm.is_active = true "
            "GROUP BY vm.category ORDER BY matched DESC"
        ))
        print("Variant mapping matches per category:")
        for row in r.fetchall():
            print(f"  {row[0]:15s}: {row[1]} matched variants")

        # Check ref_allele vs alt_alleles patterns
        r2 = await s.execute(text(
            "SELECT "
            "COUNT(*) as total, "
            "COUNT(CASE WHEN ref_allele = alt_alleles THEN 1 END) as ref_eq_alt, "
            "COUNT(CASE WHEN alt_alleles IS NULL OR alt_alleles IN ('', 'N', '-', '.') THEN 1 END) as missing_alt "
            "FROM genetic_markers "
            "WHERE ref_allele IS NOT NULL AND ref_allele NOT IN ('N', '-', '.', '')"
        ))
        row = r2.fetchone()
        print(f"\nAlt alleles quality (markers with valid ref):")
        print(f"  Total: {row[0]}, ref==alt: {row[1]}, missing alt: {row[2]}")

        # Check ref_allele coverage for registry-matched variants specifically
        r3 = await s.execute(text(
            "SELECT "
            "COUNT(*) as total, "
            "COUNT(gm.ref_allele) - COUNT(CASE WHEN gm.ref_allele IN ('N', '-', '.', '') THEN 1 END) as valid_ref, "
            "COUNT(CASE WHEN gm.ref_allele = gm.alt_alleles THEN 1 END) as ref_eq_alt "
            "FROM variant_mappings vm "
            "JOIN genetic_markers gm ON gm.rsid = vm.key "
            "JOIN analysis_variants av ON av.marker_id = gm.id "
            "WHERE av.analysis_id = (SELECT MAX(id) FROM genetic_analyses WHERE analysis_status = 'completed') "
            "AND vm.map_type = 'rsid' AND vm.is_active = true"
        ))
        row3 = r3.fetchone()
        print(f"\nRegistry-matched variants ref/alt coverage:")
        print(f"  Total: {row3[0]}, Valid ref: {row3[1]}, ref==alt: {row3[2]}")

        # Sample registry-matched variants with their genotype/ref/alt
        r4 = await s.execute(text(
            "SELECT gm.rsid, av.genotype, gm.ref_allele, gm.alt_alleles, vm.category "
            "FROM variant_mappings vm "
            "JOIN genetic_markers gm ON gm.rsid = vm.key "
            "JOIN analysis_variants av ON av.marker_id = gm.id "
            "WHERE av.analysis_id = (SELECT MAX(id) FROM genetic_analyses WHERE analysis_status = 'completed') "
            "AND vm.map_type = 'rsid' AND vm.is_active = true "
            "ORDER BY RANDOM() LIMIT 15"
        ))
        print("\nSample registry-matched (rsid | gt | ref | alt | category):")
        for row in r4.fetchall():
            print(f"  {row[0]:15s} | {str(row[1]):5s} | {str(row[2]):3s} | {str(row[3]):5s} | {row[4]}")


asyncio.run(check())
