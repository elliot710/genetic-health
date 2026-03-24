"""
Ensembl ETL — parse cDNA and ncRNA FASTA headers to build a local gene model.

Extracts gene coordinates, symbols, biotypes, and descriptions from
Ensembl FASTA header lines and bulk-loads them into the ensembl_genes table.

Data source: data_sources/ensembl/homo_sapiens/cdna/Homo_sapiens.GRCh38.cdna.all.fa.gz
             data_sources/ensembl/homo_sapiens/ncrna/Homo_sapiens.GRCh38.ncrna.fa.gz

Header format example:
  >ENST00000633705.1 cdna chromosome:GRCh38:7:142791694:142793368:1
   gene:ENSG00000211751.9 gene_biotype:TR_C_gene transcript_biotype:TR_C_gene
   gene_symbol:TRBC1 description:T cell receptor beta constant 1 [Source:HGNC Symbol;Acc:HGNC:12156]

Run via admin endpoint: POST /api/admin/ensembl-etl/import
"""

from __future__ import annotations

import gzip
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

_ENSEMBL_DATA_DIR = Path(os.environ.get(
    "ENSEMBL_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "ensembl", "homo_sapiens"),
))

_DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/genetic_health_db",
).replace("postgresql+asyncpg://", "postgresql://")

# Regex to pull key=value pairs from FASTA header
_KV_RE = re.compile(r'(\w+):(.+?)(?=\s+\w+:|$)')


def _parse_fasta_header(line: str) -> Optional[Dict[str, str]]:
    """Parse an Ensembl FASTA header line into a dict of fields.

    Returns None if the line lacks required fields (gene_symbol, location).
    """
    if not line.startswith('>'):
        return None

    parts = line[1:].split(None, 2)
    if len(parts) < 3:
        return None

    transcript_id = parts[0]
    rest = parts[2] if len(parts) > 2 else parts[1]

    # Extract location — chromosome:GRCh38:CHR:START:END:STRAND
    loc_match = re.search(r'(?:chromosome|scaffold):GRCh38:(\S+):(\d+):(\d+):(-?1)', rest)
    if not loc_match:
        return None

    chrom = loc_match.group(1)
    start = int(loc_match.group(2))
    end = int(loc_match.group(3))
    strand = int(loc_match.group(4))

    # Extract named fields
    gene_id = None
    gene_symbol = None
    biotype = None
    description = None

    m = re.search(r'gene:(ENSG\S+)', rest)
    if m:
        gene_id = m.group(1)

    m = re.search(r'gene_symbol:(\S+)', rest)
    if m:
        gene_symbol = m.group(1)

    m = re.search(r'gene_biotype:(\S+)', rest)
    if m:
        biotype = m.group(1)

    m = re.search(r'description:(.+?)(?:\s*\[Source:)', rest)
    if m:
        description = m.group(1).strip()
    elif 'description:' in rest:
        m = re.search(r'description:(.+)$', rest)
        if m:
            description = m.group(1).strip()

    if not gene_id or not gene_symbol:
        return None

    return {
        'transcript_id': transcript_id,
        'gene_id': gene_id,
        'gene_symbol': gene_symbol,
        'chromosome': chrom,
        'start': start,
        'end': end,
        'strand': strand,
        'biotype': biotype,
        'description': description,
    }


def _parse_fasta_file(path: Path) -> List[Dict[str, str]]:
    """Parse all headers from a gzipped FASTA file."""
    headers = []
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as f:
        for line in f:
            if line.startswith('>'):
                parsed = _parse_fasta_header(line.rstrip())
                if parsed:
                    headers.append(parsed)
    return headers


def _aggregate_genes(headers: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Aggregate transcript-level records into gene-level records.

    For each gene: takes the min start, max end across all transcripts.
    Keeps the first-seen biotype and description.
    """
    gene_data: Dict[str, Dict[str, Any]] = {}

    for h in headers:
        gid = h['gene_id']
        if gid not in gene_data:
            gene_data[gid] = {
                'gene_id': gid,
                'gene_symbol': h['gene_symbol'],
                'chromosome': h['chromosome'],
                'start_pos': h['start'],
                'end_pos': h['end'],
                'strand': h['strand'],
                'biotype': h['biotype'],
                'description': h['description'],
                'transcript_count': 1,
            }
        else:
            g = gene_data[gid]
            g['start_pos'] = min(g['start_pos'], h['start'])
            g['end_pos'] = max(g['end_pos'], h['end'])
            g['transcript_count'] += 1
            # Prefer protein_coding biotype and non-null descriptions
            if h['biotype'] == 'protein_coding' and g['biotype'] != 'protein_coding':
                g['biotype'] = h['biotype']
            if not g['description'] and h['description']:
                g['description'] = h['description']

    return list(gene_data.values())


class EnsemblETL:
    """Parse Ensembl FASTA headers and load gene models into PostgreSQL."""

    async def run_full_import(self) -> Dict[str, Any]:
        """Parse cDNA + ncRNA FASTAs and bulk-insert into ensembl_genes."""
        t0 = time.monotonic()

        # Locate FASTA files — files live under fasta/cdna/ and fasta/ncrna/
        fasta_base = _ENSEMBL_DATA_DIR / "fasta"
        cdna_path = fasta_base / "cdna" / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
        ncrna_path = fasta_base / "ncrna" / "Homo_sapiens.GRCh38.ncrna.fa.gz"
        # Fallback: some deploys have files directly under homo_sapiens/
        if not cdna_path.exists():
            cdna_path = _ENSEMBL_DATA_DIR / "cdna" / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
        if not ncrna_path.exists():
            ncrna_path = _ENSEMBL_DATA_DIR / "ncrna" / "Homo_sapiens.GRCh38.ncrna.fa.gz"

        all_headers: List[Dict[str, str]] = []

        if cdna_path.exists():
            logger.info(f"Parsing cDNA FASTA: {cdna_path}")
            all_headers.extend(_parse_fasta_file(cdna_path))
            logger.info(f"  → {len(all_headers)} transcript headers from cDNA")
        else:
            logger.warning(f"cDNA FASTA not found: {cdna_path}")

        ncrna_count_before = len(all_headers)
        if ncrna_path.exists():
            logger.info(f"Parsing ncRNA FASTA: {ncrna_path}")
            all_headers.extend(_parse_fasta_file(ncrna_path))
            logger.info(f"  → {len(all_headers) - ncrna_count_before} transcript headers from ncRNA")
        else:
            logger.warning(f"ncRNA FASTA not found: {ncrna_path}")

        if not all_headers:
            return {"error": "No FASTA headers parsed", "genes_loaded": 0}

        # Aggregate transcripts → genes
        genes = _aggregate_genes(all_headers)
        logger.info(f"Aggregated {len(all_headers)} transcripts → {len(genes)} unique genes")

        # Bulk insert via asyncpg COPY
        dsn = _DB_DSN
        conn = await asyncpg.connect(dsn)
        try:
            # Truncate existing data
            await conn.execute("TRUNCATE TABLE ensembl_genes RESTART IDENTITY CASCADE")

            # Use COPY for fast bulk insert
            columns = [
                'gene_id', 'gene_symbol', 'chromosome', 'start_pos', 'end_pos',
                'strand', 'biotype', 'description', 'transcript_count',
            ]
            records = [
                (
                    g['gene_id'], g['gene_symbol'], g['chromosome'],
                    g['start_pos'], g['end_pos'], g['strand'],
                    g['biotype'], g['description'], g['transcript_count'],
                )
                for g in genes
            ]

            await conn.copy_records_to_table(
                'ensembl_genes',
                records=records,
                columns=columns,
            )

            # Verify
            count = await conn.fetchval("SELECT COUNT(*) FROM ensembl_genes")
            elapsed = time.monotonic() - t0

            # Get some stats
            protein_coding = await conn.fetchval(
                "SELECT COUNT(*) FROM ensembl_genes WHERE biotype = 'protein_coding'"
            )
            chromosomes = await conn.fetchval(
                "SELECT COUNT(DISTINCT chromosome) FROM ensembl_genes"
            )

            logger.info(
                f"Ensembl ETL complete: {count} genes loaded in {elapsed:.1f}s "
                f"({protein_coding} protein-coding, {chromosomes} chromosomes)"
            )

            return {
                "genes_loaded": count,
                "protein_coding": protein_coding,
                "chromosomes": chromosomes,
                "transcripts_parsed": len(all_headers),
                "elapsed_seconds": round(elapsed, 1),
            }
        finally:
            await conn.close()
