"""
Admin reference-data ETL trigger + status routes.
"""
import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from ...db.database import get_session
from ...db.models import User
from .schemas import require_admin

# No prefix here -- folded into admin_routes.router, which already carries
# "/api/admin"; baking it in twice double-prefixes (see admin_routes.py).
router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)


# ======================================================================
# ClinVar ETL endpoints
# ======================================================================

@router.get("/clinvar-etl/status")
async def clinvar_etl_status(admin: User = Depends(require_admin)):
    """Get current ClinVar import status (row counts + file availability)."""
    from ...services.clinvar_etl import ClinVarETL
    etl = ClinVarETL()
    return await etl.get_import_status()


@router.get("/clinvar-etl/progress")
async def clinvar_etl_progress(admin: User = Depends(require_admin)):
    """Return live progress of the running (or last) ClinVar ETL import."""
    from ...services.clinvar_etl import get_etl_progress
    return get_etl_progress()


@router.post("/clinvar-etl/import")
async def clinvar_etl_import(admin: User = Depends(require_admin)):
    """Kick off a ClinVar ETL import in the background and return immediately.
    Poll GET /clinvar-etl/progress for live status."""
    from ...services.clinvar_etl import ClinVarETL, get_etl_progress

    # Reject concurrent imports
    prog = get_etl_progress()
    if prog.get("running"):
        return {"status": "already_running", "step": prog.get("step"), "pct": prog.get("pct")}

    async def _run():
        etl = ClinVarETL()
        try:
            await etl.run_full_import()
            # Refresh the ClinVar local service cache count
            from ...services.clinvar_local import get_clinvar_local_service
            cv_svc = get_clinvar_local_service()
            await cv_svc.ensure_loaded()
        except Exception:
            pass  # errors are recorded in _etl_progress

    import asyncio as _asyncio
    _asyncio.create_task(_run())
    return {"status": "started"}


# ======================================================================
# GWAS Catalog ETL endpoints
# ======================================================================

@router.get("/gwas-catalog-etl/progress")
async def gwas_catalog_etl_progress(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    from ...services.gwas_catalog_etl import get_etl_progress
    from sqlalchemy import text
    prog = get_etl_progress()
    if not prog.get("running"):
        result = await db.execute(text("SELECT COUNT(*) FROM gwas_catalog_associations"))
        prog = dict(prog)
        prog["rows"] = result.scalar() or 0
    return prog


@router.post("/gwas-catalog-etl/import")
async def gwas_catalog_etl_import(admin: User = Depends(require_admin)):
    from ...services.gwas_catalog_etl import run_gwas_etl, get_etl_progress
    prog = get_etl_progress()
    if prog.get("running"):
        return {"status": "already_running", "step": prog.get("step"), "pct": prog.get("pct")}

    async def _run():
        try:
            await run_gwas_etl()
            from ...services.gwas_catalog_local import get_gwas_catalog_service
            await get_gwas_catalog_service().ensure_loaded()
        except Exception:
            pass

    import asyncio as _asyncio
    _asyncio.create_task(_run())
    return {"status": "started"}


# ======================================================================
# ClinGen ETL endpoints
# ======================================================================

@router.get("/clingen-etl/progress")
async def clingen_etl_progress(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    from ...services.clingen_etl import get_etl_progress
    from sqlalchemy import text
    prog = get_etl_progress()
    if not prog.get("running"):
        result = await db.execute(text("SELECT COUNT(*) FROM clingen_gene_validity"))
        prog = dict(prog)
        prog["rows"] = result.scalar() or 0
    return prog


@router.post("/clingen-etl/import")
async def clingen_etl_import(admin: User = Depends(require_admin)):
    from ...services.clingen_etl import run_clingen_etl, get_etl_progress
    prog = get_etl_progress()
    if prog.get("running"):
        return {"status": "already_running", "step": prog.get("step"), "pct": prog.get("pct")}

    async def _run():
        try:
            await run_clingen_etl()
            from ...services.clingen_local import get_clingen_service
            await get_clingen_service().ensure_loaded()
        except Exception:
            pass

    import asyncio as _asyncio
    _asyncio.create_task(_run())
    return {"status": "started"}


# ======================================================================
# Open Targets test endpoint
# ======================================================================

@router.get("/open-targets/test")
async def open_targets_test(admin: User = Depends(require_admin)):
    from ...services.open_targets_service import get_open_targets_service
    svc = get_open_targets_service()
    try:
        result = await svc.lookup_by_gene("BRCA1")
        return {
            "status": "ok",
            "reachable": True,
            "test_gene": "BRCA1",
            "found": result.get("found", False),
            "association_count": len(result.get("associations", [])),
            "top_disease": result.get("top_disease"),
            "max_score": result.get("max_score"),
        }
    except Exception as exc:
        return {"status": "error", "reachable": False, "error": str(exc)}


# ======================================================================
# gnomAD ETL endpoints
# ======================================================================

@router.get("/gnomad-etl/status")
async def gnomad_etl_status(admin: User = Depends(require_admin)):
    """Get current gnomAD import status (row counts + file availability)."""
    from ...services.gnomad_etl import GnomadETL
    etl = GnomadETL()
    return await etl.get_import_status()


@router.post("/gnomad-etl/import")
async def gnomad_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch gnomAD ETL to the background worker and return immediately."""
    from ...db.models import WorkerJob
    job = WorkerJob(job_type="etl_gnomad", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


@router.post("/gnomad/build-cadd-cache")
async def gnomad_build_cadd_cache(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Queue a worker job to build the gnomAD CADD SQLite cache via sequential scan.

    After this completes, all analysis gnomAD lookups hit SQLite (sub-second)
    instead of doing 609K per-variant tabix seeks (~14 min).
    """
    from ...db.models import WorkerJob
    job = WorkerJob(job_type="gnomad_build_cadd_cache", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD CADD cache build job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD CADD cache build queued as worker job #{job.id}"}


@router.post("/gnomad/refresh-ancestry-afs")
async def gnomad_refresh_ancestry_afs(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    fst_threshold: float = 0.70,
    index_first: bool = False,
):
    """Queue a worker job to refresh ancestry_aims_panel with gnomAD v2 AFs.

    Reads from local GRCh37 VCF files — no network calls needed.
    Replaces the data previously loaded via the gnomAD GraphQL API.

    index_first=true will create .tbi indexes for any unindexed VCF files first.
    """
    from ...db.models import WorkerJob
    job = WorkerJob(
        job_type="gnomad_refresh_ancestry_afs",
        status="pending",
        params={"fst_threshold": fst_threshold, "index_first": index_first},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD ancestry AF refresh job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD ancestry AF refresh queued as worker job #{job.id}"}


@router.get("/gnomad/v2-status")
async def gnomad_v2_status(admin: User = Depends(require_admin)):
    """Get gnomAD v2 VCF file availability and index status."""
    from ...services.gnomad_v2_local import get_gnomad_v2_service
    svc = get_gnomad_v2_service()
    if not svc.is_loaded:
        await svc.ensure_loaded()
    return {
        "file_count": svc.file_count,
        "indexed_count": svc.indexed_count,
        "pg_rows": svc._pg_count,
        "ready": svc.has_pg_data or svc.indexed_count > 0,
    }


# ======================================================================
# gnomAD v2 exome ETL endpoints
# ======================================================================

@router.get("/gnomad-v2-etl/status")
async def gnomad_v2_etl_status(admin: User = Depends(require_admin)):
    """Get current gnomAD v2 exome import status (row counts + file availability)."""
    from ...services.gnomad_v2_etl import GnomadV2ETL
    etl = GnomadV2ETL()
    return await etl.get_import_status()


@router.post("/gnomad-v2-etl/import")
async def gnomad_v2_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch gnomAD v2 exome ETL to the background worker and return immediately."""
    from ...db.models import WorkerJob
    # Prevent duplicate pending/processing jobs
    existing = (await db.execute(
        select(WorkerJob).where(
            WorkerJob.job_type == "etl_gnomad_v2",
            WorkerJob.status.in_(["pending", "processing"]),
        )
    )).scalars().first()
    if existing:
        return {"job_id": existing.id, "status": existing.status,
                "detail": f"gnomAD v2 ETL already {existing.status} (job #{existing.id})"}
    job = WorkerJob(job_type="etl_gnomad_v2", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD v2 ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD v2 ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


# ======================================================================
# AlphaFold ETL endpoints
# ======================================================================

@router.get("/alphafold-etl/status")
async def alphafold_etl_status(admin: User = Depends(require_admin)):
    """Get AlphaFold local data status (SQLite DB protein count)."""
    from ...services.alphafold_local import get_alphafold_local_service
    svc = get_alphafold_local_service()
    if not svc.available:
        svc.ensure_loaded()
    return {
        "alphafold_proteins": svc.protein_count,
        "loaded": svc.available,
        "db_exists": svc._db_path.exists(),
        "db_path": str(svc._db_path),
    }


@router.post("/alphafold-etl/import")
async def alphafold_etl_import(
    force: bool = Query(False, description="Rebuild even if DB already exists"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch AlphaFold ETL (download + build SQLite) to the background worker."""
    from ...db.models import WorkerJob
    # Prevent duplicate pending/processing jobs
    existing = (await db.execute(
        select(WorkerJob).where(
            WorkerJob.job_type == "etl_alphafold",
            WorkerJob.status.in_(["pending", "processing"]),
        )
    )).scalars().first()
    if existing:
        return {"job_id": existing.id, "status": existing.status,
                "detail": f"AlphaFold ETL already {existing.status} (job #{existing.id})"}
    job = WorkerJob(
        job_type="etl_alphafold",
        status="pending",
        params={"force": force},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"AlphaFold ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"AlphaFold ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


@router.get("/ensembl-etl/status")
async def ensembl_etl_status(admin: User = Depends(require_admin)):
    """Get current Ensembl gene model import status (row counts + file availability)."""
    import os
    from pathlib import Path
    from sqlalchemy import text as sa_text
    from ...db.database import async_session_factory
    async with async_session_factory() as session:
        total = (await session.execute(sa_text("SELECT COUNT(*) FROM ensembl_genes"))).scalar() or 0
        protein_coding = (await session.execute(
            sa_text("SELECT COUNT(*) FROM ensembl_genes WHERE biotype = 'protein_coding'")
        )).scalar() or 0
        chromosomes = (await session.execute(
            sa_text("SELECT COUNT(DISTINCT chromosome) FROM ensembl_genes")
        )).scalar() or 0
    data_dir = Path(os.environ.get(
        "ENSEMBL_DATA_DIR",
        os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "ensembl", "homo_sapiens"),
    ))
    fasta_base = data_dir / "fasta"
    cdna_path = fasta_base / "cdna" / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    ncrna_path = fasta_base / "ncrna" / "Homo_sapiens.GRCh38.ncrna.fa.gz"
    if not cdna_path.exists():
        cdna_path = data_dir / "cdna" / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    if not ncrna_path.exists():
        ncrna_path = data_dir / "ncrna" / "Homo_sapiens.GRCh38.ncrna.fa.gz"
    return {
        "ensembl_genes": total,
        "protein_coding_genes": protein_coding,
        "chromosomes": chromosomes,
        "cdna_file_exists": cdna_path.exists(),
        "ncrna_file_exists": ncrna_path.exists(),
    }


@router.post("/ensembl-etl/import")
async def ensembl_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch Ensembl gene model ETL to the background worker and return immediately."""
    from ...db.models import WorkerJob
    job = WorkerJob(job_type="etl_ensembl", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"Ensembl ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"Ensembl ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


# ======================================================================
# 1000 Genomes Phase 3 ETL endpoints
# ======================================================================

@router.get("/1kg-etl/status")
async def thousand_genomes_etl_status(admin: User = Depends(require_admin)):
    """Get current 1000 Genomes import status (row count + file availability)."""
    from ...services.thousand_genomes_etl import ThousandGenomesETL
    etl = ThousandGenomesETL()
    return await etl.get_import_status()


@router.post("/1kg-etl/import")
async def thousand_genomes_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch 1000 Genomes ETL to the background worker and return immediately."""
    from ...db.models import WorkerJob
    job = WorkerJob(job_type="etl_1kg", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"1000 Genomes ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"1000 Genomes ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


# ======================================================================
# gnomAD BigQuery backfill endpoints
# ======================================================================

@router.get("/gnomad-bigquery/status")
async def gnomad_bigquery_status(admin: User = Depends(require_admin)):
    """Get BigQuery backfill status — enrichment progress, BQ availability."""
    from ...services.gnomad_bigquery import GnomadBackfillService
    svc = GnomadBackfillService()
    return await svc.get_backfill_status()


@router.post("/gnomad-bigquery/backfill")
async def gnomad_bigquery_backfill(
    batch_size: int = Query(200, ge=10, le=1000, description="Variants per BigQuery query"),
    max_variants: int = Query(10000, ge=100, le=1000000, description="Max variants to process"),
    chromosome: Optional[str] = Query(None, description="Only backfill this chromosome (1-22, X, Y)"),
    admin: User = Depends(require_admin),
):
    """Run BigQuery backfill — enrich local CADD variants with population AFs.
    This queries Google BigQuery and may incur costs. Uses 10 GB byte budget per query."""
    from ...services.gnomad_bigquery import GnomadBackfillService
    svc = GnomadBackfillService()
    return await svc.backfill(
        batch_size=batch_size,
        max_variants=max_variants,
        chromosome=chromosome,
    )

