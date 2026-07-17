"""Rebuild the offline consequence caches over the current marker set (U6).

Exports genetic_markers to a VCF, runs VEP + SnpEff offline over it, and rebuilds
all four caches (MANE, dbSNP MC, VEP, SnpEff). Run on the worker box after the
setup script has downloaded the sources + installed the tools, and again whenever
the marker set grows. This is an ops/refresh action (requires the DB, VEP, and
SnpEff) — not exercised by unit tests.

Usage (inside backend container):
  uv run python -m backend.scripts.refresh_consequence_caches
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select

from backend.db.database import async_session_factory
from backend.db.models import GeneticMarker
from backend.services.annotation_sources.mane_cache import build_mane_cache, ManeCache
from backend.services.annotation_sources.dbsnp_mc_cache import build_dbsnp_mc_cache
from backend.services.annotation_sources.vep_offline_cache import run_vep, build_vep_cache
from backend.services.annotation_sources.snpeff_offline_cache import run_snpeff, build_snpeff_cache

_DATA = "data_sources"
_WORK = ".consequence_build"
_MANE_SUMMARY = f"{_DATA}/mane/MANE.GRCh38.v1.5.summary.txt.gz"
_DBSNP_VCF = f"{_DATA}/dbsnp/00-All.GRCh37.vcf.gz"
_VEP_CACHE_DIR = f"{_DATA}/ensembl/vep_cache"
_SNPEFF_JAR = f"{_DATA}/snpeff/snpEff/snpEff.jar"


async def export_markers_vcf(vcf_path: str) -> int:
    os.makedirs(os.path.dirname(vcf_path), exist_ok=True)
    written = 0
    with open(vcf_path, "w") as out:
        out.write("##fileformat=VCFv4.1\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
        async with async_session_factory() as session:
            result = await session.stream(
                select(
                    GeneticMarker.chromosome, GeneticMarker.position,
                    GeneticMarker.rsid, GeneticMarker.ref_allele, GeneticMarker.alt_alleles,
                )
            )
            async for chrom, pos, rsid, ref, alts in result:
                alt = (alts or "").split(",")[0].strip() or "."
                if not (chrom and pos and ref):
                    continue
                out.write(f"{chrom}\t{pos}\t{rsid}\t{ref}\t{alt}\t.\t.\t.\n")
                written += 1
    return written


async def main() -> None:
    os.makedirs(_WORK, exist_ok=True)
    marker_vcf = f"{_WORK}/markers.vcf"

    print("Exporting marker set to VCF...")
    n = await export_markers_vcf(marker_vcf)
    print(f"  {n} markers exported")

    print("Building MANE cache...")
    build_mane_cache(_MANE_SUMMARY, ".mane_cache/mane.db")
    mane = ManeCache(".mane_cache/mane.db")

    print("Building dbSNP MC cache...")
    build_dbsnp_mc_cache(_DBSNP_VCF, ".dbsnp_cache/dbsnp_mc.db")

    print("Running VEP offline over markers...")
    vep_out = f"{_WORK}/vep.tab"
    run_vep(marker_vcf, _VEP_CACHE_DIR, vep_out, assembly="GRCh37")
    print("  VEP rows cached:", build_vep_cache(vep_out, ".vep_cache/vep_consequence.db", mane_cache=mane))

    print("Running SnpEff offline over markers...")
    snpeff_out = f"{_WORK}/snpeff.vcf"
    run_snpeff(marker_vcf, _SNPEFF_JAR, "GRCh37.75", snpeff_out)
    print("  SnpEff rows cached:", build_snpeff_cache(snpeff_out, ".snpeff_cache/snpeff_consequence.db", mane_cache=mane))

    print("Done — all four consequence caches rebuilt.")


if __name__ == "__main__":
    asyncio.run(main())
