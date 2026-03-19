"""
ETL service to load Ensembl VEP consequences from VCF dumps into PostgreSQL.

Parses homo_sapiens_incl_consequences-chr*.vcf.gz files and populates the
ensembl_vep_variants table.  Only imports variants that exist in our
genetic_markers table (filtered ETL) to keep the table manageable.

Admin trigger:  POST /api/admin/ensembl-vep-etl/import
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import asyncpg

from .datasource_utils import parse_vcf_info

logger = logging.getLogger(__name__)

_ENSEMBL_DATA_DIR = Path(os.environ.get(
    'ENSEMBL_DATA_DIR',
    '/app/data_sources/ensembl/homo_sapiens',
))
_VCF_VEP_DIR = _ENSEMBL_DATA_DIR / 'variation' / 'vcf_vep'
_DB_DSN = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:postgres@postgres:5432/genetic_health_db',
).replace('+asyncpg', '').replace('postgresql+psycopg2', 'postgresql')

# Chromosome file pattern
_CHR_PATTERN = re.compile(r'homo_sapiens_incl_consequences-chr(\w+)\.vcf\.gz$')

# ── VEP consequence → impact mapping (SO terms) ──────────────────────
CONSEQUENCE_IMPACT: Dict[str, str] = {
    'transcript_ablation': 'HIGH',
    'splice_acceptor_variant': 'HIGH',
    'splice_donor_variant': 'HIGH',
    'stop_gained': 'HIGH',
    'frameshift_variant': 'HIGH',
    'stop_lost': 'HIGH',
    'start_lost': 'HIGH',
    'transcript_amplification': 'HIGH',
    'feature_elongation': 'HIGH',
    'feature_truncation': 'HIGH',
    'inframe_insertion': 'MODERATE',
    'inframe_deletion': 'MODERATE',
    'missense_variant': 'MODERATE',
    'protein_altering_variant': 'MODERATE',
    'splice_donor_5th_base_variant': 'LOW',
    'splice_region_variant': 'LOW',
    'splice_donor_region_variant': 'LOW',
    'splice_polypyrimidine_tract_variant': 'LOW',
    'incomplete_terminal_codon_variant': 'LOW',
    'start_retained_variant': 'LOW',
    'stop_retained_variant': 'LOW',
    'synonymous_variant': 'LOW',
}

_IMPACT_SEVERITY = {'HIGH': 0, 'MODERATE': 1, 'LOW': 2, 'MODIFIER': 3}


def _impact_for(consequence: str) -> str:
    return CONSEQUENCE_IMPACT.get(consequence, 'MODIFIER')


def _worst_impact(impacts: List[str]) -> str:
    return min(impacts, key=lambda i: _IMPACT_SEVERITY.get(i, 3))


# ── VCF line parsing ─────────────────────────────────────────────────

def _parse_sift_polyphen(raw: str) -> List[Tuple[int, str, float, str]]:
    """Parse Sift or Polyphen INFO fields.
    Format: Index|prediction|score|Feature_id[,...]
    """
    entries = []
    for entry in raw.split(','):
        parts = entry.split('|')
        if len(parts) >= 4:
            try:
                idx = int(parts[0])
                pred = parts[1].replace('_', ' ').replace(' - ', '-')
                score = float(parts[2]) if parts[2] else None
                feature = parts[3]
                entries.append((idx, pred, score, feature))
            except (ValueError, IndexError):
                continue
    return entries


def _parse_csq(csq_str: str) -> List[Dict[str, Any]]:
    """Parse CSQ INFO field.
    Format: Allele|Consequence|Feature_type|Feature|Amino_acids|SIFT[,...]
    """
    entries = []
    for entry in csq_str.split(','):
        parts = entry.split('|')
        if len(parts) >= 4:
            d: Dict[str, Any] = {
                'allele': parts[0],
                'consequence': parts[1],
                'feature_type': parts[2] or None,
                'feature_id': parts[3] or None,
                'amino_acids': parts[4] if len(parts) > 4 and parts[4] else None,
                'sift_raw': parts[5] if len(parts) > 5 and parts[5] else None,
            }
            entries.append(d)
    return entries


def _parse_sift_from_csq(raw: str) -> Tuple[Optional[str], Optional[float]]:
    """Parse SIFT from CSQ field e.g. 'deleterious_-_low_confidence(0.01)'."""
    if not raw:
        return None, None
    m = re.match(r'(.+?)\(([0-9.]+)\)', raw)
    if m:
        pred = m.group(1).replace('_', ' ').replace(' - ', '-')
        return pred, float(m.group(2))
    return raw.replace('_', ' '), None


def parse_vcf_line(
    line: str,
    known_rsids: Optional[Set[str]],
    gene_lookup: Optional[Dict[str, List[Tuple[int, int, str, str]]]] = None,
) -> Optional[Dict[str, Any]]:
    """Parse a single VCF data line into a dict for DB insertion.

    Returns None if the line should be skipped (no rsid match, header, etc.).
    """
    if line.startswith('#'):
        return None

    parts = line.rstrip('\n').split('\t', 8)
    if len(parts) < 8:
        return None

    chrom, pos_str, rsid, ref, alt, _, _, info_raw = parts[:8]

    if not rsid.startswith('rs'):
        return None
    if known_rsids is not None and rsid not in known_rsids:
        return None

    pos = int(pos_str)
    info = parse_vcf_info(info_raw)

    # ── Basic fields ──
    variant_type = info.get('TSA')
    minor_allele = info.get('MA')
    maf = float(info['MAF']) if 'MAF' in info and info['MAF'] else None
    ancestral = info.get('AA')

    # ── Evidence flags ──
    evidence = [k[2:] for k in info if k.startswith('E_')]

    # ── Clinical significance flags ──
    clin_sig = [k[5:].replace('_', ' ') for k in info if k.startswith('CLIN_')]

    # ── Parse VEP consequence data ──
    csq_entries = _parse_csq(info.get('CSQ', '')) if 'CSQ' in info else []

    # Sift / Polyphen from separate INFO fields (more detailed than CSQ)
    sift_entries = _parse_sift_polyphen(info['Sift']) if 'Sift' in info else []
    pp_entries = _parse_sift_polyphen(info['Polyphen']) if 'Polyphen' in info else []

    # Build sift/polyphen lookup by (index, feature_id)
    sift_map: Dict[Tuple[int, str], Tuple[str, Optional[float]]] = {}
    for idx, pred, score, feat in sift_entries:
        sift_map[(idx, feat)] = (pred, score)

    pp_map: Dict[Tuple[int, str], Tuple[str, Optional[float]]] = {}
    for idx, pred, score, feat in pp_entries:
        pp_map[(idx, feat)] = (pred, score)

    # Build transcript_consequences array (API-compatible format)
    transcript_consequences: List[Dict[str, Any]] = []
    all_impacts: List[str] = []

    for ci, csq in enumerate(csq_entries):
        consequence = csq['consequence']
        impact = _impact_for(consequence)
        all_impacts.append(impact)

        tc: Dict[str, Any] = {
            'consequence_terms': [consequence],
            'impact': impact,
        }

        if csq['feature_type']:
            tc['feature_type'] = csq['feature_type']
        if csq['feature_id']:
            tc['transcript_id'] = csq['feature_id']
        if csq['amino_acids']:
            tc['amino_acids'] = csq['amino_acids']

        # SIFT — prefer the separate Sift field (has feature-level detail)
        feat = csq['feature_id'] or ''
        sift_key = (ci, feat)
        if sift_key in sift_map:
            pred, score = sift_map[sift_key]
            tc['sift_prediction'] = pred
            if score is not None:
                tc['sift_score'] = score
        elif csq['sift_raw']:
            pred, score = _parse_sift_from_csq(csq['sift_raw'])
            if pred:
                tc['sift_prediction'] = pred
            if score is not None:
                tc['sift_score'] = score

        # PolyPhen
        pp_key = (ci, feat)
        if pp_key in pp_map:
            pred, score = pp_map[pp_key]
            tc['polyphen_prediction'] = pred
            if score is not None:
                tc['polyphen_score'] = score

        # Gene symbol from position lookup
        if gene_lookup and chrom in gene_lookup:
            gene_sym = _find_gene(gene_lookup[chrom], pos)
            if gene_sym:
                tc['gene_symbol'] = gene_sym

        transcript_consequences.append(tc)

    # If no CSQ entries but VE field exists, fall back to VE
    if not transcript_consequences and 'VE' in info:
        for ve_entry in info['VE'].split(','):
            ve_parts = ve_entry.split('|')
            if len(ve_parts) >= 1:
                consequence = ve_parts[0]
                impact = _impact_for(consequence)
                all_impacts.append(impact)
                tc = {
                    'consequence_terms': [consequence],
                    'impact': impact,
                }
                if len(ve_parts) >= 4 and ve_parts[2]:
                    tc['feature_type'] = ve_parts[2]
                if len(ve_parts) >= 4 and ve_parts[3]:
                    tc['transcript_id'] = ve_parts[3]
                if gene_lookup and chrom in gene_lookup:
                    gene_sym = _find_gene(gene_lookup[chrom], pos)
                    if gene_sym:
                        tc['gene_symbol'] = gene_sym
                transcript_consequences.append(tc)

    # Determine most severe consequence + impact
    most_severe = None
    worst_impact = 'MODIFIER'
    if transcript_consequences:
        most_severe = transcript_consequences[0]['consequence_terms'][0]
        worst_impact = _worst_impact(all_impacts) if all_impacts else 'MODIFIER'
        # Reorder: pick the one with worst impact
        for tc_item in transcript_consequences:
            if tc_item['impact'] == worst_impact:
                most_severe = tc_item['consequence_terms'][0]
                break

    # Gene symbol — from best consequence
    gene_symbol = None
    for tc_item in transcript_consequences:
        if tc_item.get('gene_symbol'):
            gene_symbol = tc_item['gene_symbol']
            if tc_item['impact'] == worst_impact:
                break  # prefer gene from worst impact

    # Build the full API-compatible data dict
    allele_string = f"{ref}/{alt}"
    vep_data = {
        'found': True,
        'source': 'ensembl',
        'data': [{
            'allele_string': allele_string,
            'seq_region_name': chrom,
            'start': pos,
            'most_severe_consequence': most_severe,
            'transcript_consequences': transcript_consequences,
        }],
    }

    # Add colocated_variants with MAF if available
    if maf is not None and minor_allele:
        vep_data['data'][0]['colocated_variants'] = [{
            'id': rsid,
            'minor_allele': minor_allele,
            'minor_allele_freq': maf,
            'frequencies': {
                minor_allele: {'gnomade': maf},
            },
        }]

    return {
        'rsid': rsid,
        'chromosome': chrom,
        'position': pos,
        'ref_allele': ref,
        'alt_alleles': alt,
        'variant_type': variant_type,
        'minor_allele': minor_allele,
        'minor_allele_freq': maf,
        'ancestral_allele': ancestral,
        'clinical_significance': clin_sig or None,
        'evidence': evidence or None,
        'most_severe_consequence': most_severe,
        'impact': worst_impact,
        'gene_symbol': gene_symbol,
        'vep_data': json.dumps(vep_data),
    }


def _find_gene(
    genes: List[Tuple[int, int, str, str]],  # (start, end, symbol, biotype)
    pos: int,
) -> Optional[str]:
    """Binary-search-ish find gene overlapping a position."""
    best = None
    best_size = float('inf')
    for start, end, symbol, biotype in genes:
        if start <= pos <= end:
            size = end - start
            # Prefer protein_coding, then smallest
            if biotype == 'protein_coding' and best is None:
                best = symbol
                best_size = size
            elif size < best_size:
                best = symbol
                best_size = size
    return best


# ── Gene lookup builder ──────────────────────────────────────────────

async def _build_gene_lookup(conn: asyncpg.Connection) -> Dict[str, List[Tuple[int, int, str, str]]]:
    """Build an in-memory chrom → [(start, end, symbol, biotype)] lookup
    from the ensembl_genes table for gene symbol annotation during ETL."""
    rows = await conn.fetch(
        "SELECT chromosome, start_pos, end_pos, gene_symbol, biotype "
        "FROM ensembl_genes ORDER BY chromosome, start_pos"
    )
    lookup: Dict[str, List[Tuple[int, int, str, str]]] = {}
    for r in rows:
        chrom = r['chromosome']
        lookup.setdefault(chrom, []).append(
            (r['start_pos'], r['end_pos'], r['gene_symbol'], r['biotype'] or '')
        )
    logger.info(f"Gene lookup: {len(rows)} genes across {len(lookup)} chromosomes")
    return lookup


# ── Main ETL class ───────────────────────────────────────────────────

class EnsemblVepETL:
    """Parse Ensembl VEP VCF files and load into ensembl_vep_variants table."""

    def _discover_vcf_files(self) -> List[Tuple[str, Path]]:
        """Find all available incl_consequences VCF files, return (chrom, path) pairs."""
        files = []
        if not _VCF_VEP_DIR.exists():
            logger.warning(f"VCF VEP directory not found: {_VCF_VEP_DIR}")
            return files
        for p in sorted(_VCF_VEP_DIR.iterdir()):
            m = _CHR_PATTERN.match(p.name)
            if m:
                files.append((m.group(1), p))
        return files

    def _discover_special_vcf_files(self) -> List[Tuple[str, Path]]:
        """Find clinically_associated and phenotype_associated VCF files."""
        specials = []
        if not _VCF_VEP_DIR.exists():
            return specials
        for name, label in [
            ('homo_sapiens_clinically_associated.vcf.gz', 'clinically_associated'),
            ('homo_sapiens_phenotype_associated.vcf.gz', 'phenotype_associated'),
        ]:
            p = _VCF_VEP_DIR / name
            if p.exists():
                specials.append((label, p))
        return specials

    async def _load_known_rsids(self, conn: asyncpg.Connection) -> Set[str]:
        """Load all rsids from genetic_markers table."""
        rows = await conn.fetch("SELECT rsid FROM genetic_markers WHERE rsid IS NOT NULL")
        rsids = {r['rsid'] for r in rows}
        logger.info(f"Loaded {len(rsids)} known rsids from genetic_markers")
        return rsids

    async def _loaded_chromosomes(self, conn: asyncpg.Connection) -> Set[str]:
        """Return chromosomes already loaded in ensembl_vep_variants."""
        rows = await conn.fetch(
            "SELECT DISTINCT chromosome FROM ensembl_vep_variants"
        )
        return {r['chromosome'] for r in rows}

    async def run_import(
        self,
        *,
        filter_to_known: bool = True,
        force_reload: bool = False,
        chromosomes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Import VEP data from VCF files.

        Args:
            filter_to_known: Only import rsids that exist in genetic_markers.
            force_reload: Re-import even if chromosome data already exists.
            chromosomes: Limit to these chromosomes (e.g. ['1', '22', 'X']).
        """
        t0 = time.monotonic()
        vcf_files = self._discover_vcf_files()
        if not vcf_files:
            return {'error': 'No VCF files found', 'dir': str(_VCF_VEP_DIR)}

        conn = await asyncpg.connect(_DB_DSN)
        try:
            known_rsids: Optional[Set[str]] = None
            if filter_to_known:
                known_rsids = await self._load_known_rsids(conn)
                if not known_rsids:
                    return {'error': 'No rsids in genetic_markers — upload data first'}

            gene_lookup = await _build_gene_lookup(conn)

            already_loaded = await self._loaded_chromosomes(conn) if not force_reload else set()

            total_imported = 0
            total_skipped = 0
            chr_stats: Dict[str, int] = {}

            for chrom, vcf_path in vcf_files:
                if chromosomes and chrom not in chromosomes:
                    continue
                if chrom in already_loaded:
                    logger.info(f"Skipping chr{chrom} — already loaded")
                    total_skipped += 1
                    continue

                count = await self._import_chromosome(
                    conn, vcf_path, chrom, known_rsids, gene_lookup
                )
                chr_stats[chrom] = count
                total_imported += count

            # ── Also import clinically_associated & phenotype_associated VCFs ──
            special_stats: Dict[str, int] = {}
            for label, vcf_path in self._discover_special_vcf_files():
                if label in already_loaded:
                    logger.info(f"Skipping {label} — already loaded")
                    continue
                count = await self._import_chromosome(
                    conn, vcf_path, label, known_rsids, gene_lookup
                )
                special_stats[label] = count
                total_imported += count

            elapsed = time.monotonic() - t0

            # Get total count
            total_rows = await conn.fetchval(
                "SELECT COUNT(*) FROM ensembl_vep_variants"
            )

            logger.info(
                f"Ensembl VEP ETL complete: {total_imported} new variants from "
                f"{len(chr_stats)} chromosomes in {elapsed:.1f}s "
                f"(total in table: {total_rows})"
            )

            return {
                'variants_imported': total_imported,
                'chromosomes_processed': chr_stats,
                'special_files_processed': special_stats,
                'chromosomes_skipped': total_skipped,
                'total_in_table': total_rows,
                'elapsed_seconds': round(elapsed, 1),
                'filter_mode': 'known_rsids' if filter_to_known else 'all',
            }
        finally:
            await conn.close()

    async def _import_chromosome(
        self,
        conn: asyncpg.Connection,
        vcf_path: Path,
        chrom: str,
        known_rsids: Optional[Set[str]],
        gene_lookup: Dict[str, List[Tuple[int, int, str, str]]],
    ) -> int:
        """Import a single chromosome VCF file.  Returns count of imported rows."""
        logger.info(f"Importing {chrom} from {vcf_path.name}")
        t0 = time.monotonic()

        records = []
        lines_read = 0

        with gzip.open(vcf_path, 'rt') as f:
            for line in f:
                if line.startswith('#'):
                    continue
                lines_read += 1

                parsed = parse_vcf_line(line, known_rsids, gene_lookup)
                if parsed:
                    records.append((
                        parsed['rsid'],
                        parsed['chromosome'],
                        parsed['position'],
                        parsed['ref_allele'],
                        parsed['alt_alleles'],
                        parsed['variant_type'],
                        parsed['minor_allele'],
                        parsed['minor_allele_freq'],
                        parsed['ancestral_allele'],
                        parsed['clinical_significance'],
                        parsed['evidence'],
                        parsed['most_severe_consequence'],
                        parsed['impact'],
                        parsed['gene_symbol'],
                        parsed['vep_data'],
                    ))

                if lines_read % 5_000_000 == 0:
                    logger.info(
                        f"  {chrom}: read {lines_read:,} lines, "
                        f"{len(records):,} matched"
                    )

        if not records:
            logger.info(f"  {chrom}: no matching variants in {lines_read:,} lines")
            return 0

        # Bulk insert using COPY + temp table for conflict handling
        async with conn.transaction():
            await conn.execute(
                "CREATE TEMP TABLE _vep_staging "
                "(LIKE ensembl_vep_variants INCLUDING DEFAULTS) "
                "ON COMMIT DROP"
            )

            columns = [
                'rsid', 'chromosome', 'position', 'ref_allele', 'alt_alleles',
                'variant_type', 'minor_allele', 'minor_allele_freq', 'ancestral_allele',
                'clinical_significance', 'evidence', 'most_severe_consequence',
                'impact', 'gene_symbol', 'vep_data',
            ]

            await conn.copy_records_to_table(
                '_vep_staging', records=records, columns=columns,
            )

            result = await conn.fetchval("""
                WITH inserted AS (
                    INSERT INTO ensembl_vep_variants (
                        rsid, chromosome, position, ref_allele, alt_alleles,
                        variant_type, minor_allele, minor_allele_freq, ancestral_allele,
                        clinical_significance, evidence, most_severe_consequence,
                        impact, gene_symbol, vep_data
                    )
                    SELECT rsid, chromosome, position, ref_allele, alt_alleles,
                           variant_type, minor_allele, minor_allele_freq, ancestral_allele,
                           clinical_significance, evidence, most_severe_consequence,
                           impact, gene_symbol, vep_data::json
                    FROM _vep_staging
                    ON CONFLICT (rsid) DO NOTHING
                    RETURNING 1
                )
                SELECT COUNT(*) FROM inserted
            """)
            actual_inserted = result or len(records)

        elapsed = time.monotonic() - t0
        logger.info(
            f"  {chrom}: imported {actual_inserted:,} variants "
            f"from {lines_read:,} lines ({elapsed:.1f}s)"
        )
        return actual_inserted
