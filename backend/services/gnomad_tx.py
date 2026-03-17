"""
gnomAD transcript annotation service — gene/consequence/LoF/GTEx tissue expression.

Provides position-based lookups against the gnomAD tx_annotated file:
    all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz

This file contains ALL possible single-nucleotide variants annotated with
transcript-level data: gene symbol, VEP consequence, LoF status, and
GTEx v7 tissue-specific expression proportions.

Data columns: chrom, pos, ref, alt, tx_annotation (JSON array)
Each tx_annotation entry has:
  - ensg: Ensembl gene ID
  - symbol: gene symbol
  - csq: VEP consequence term
  - lof: LoF classification (HC, LC, or null)
  - lof_flag: LoF flag
  - ~50 GTEx tissue expression proportions
  - mean_proportion: average across tissues

Expected files in GNOMAD_DATA_DIR:
  - all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz
  - all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz.tbi
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get(
    "GNOMAD_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "gnomad"),
))

_TX_FILE = "all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz"

# Fields in the tx_annotation JSON that are NOT tissue names
_STANDARD_FIELDS = frozenset({
    "ensg", "csq", "symbol", "lof", "lof_flag", "mean_proportion",
})


class GnomadTxService:
    """Lookup service for gnomAD transcript annotations with GTEx tissue expression.

    Uses pysam.TabixFile for O(log n) random-access lookups by genomic position.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = Path(data_dir) if data_dir else DATA_DIR
        self._tabix = None
        self._available: Optional[bool] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        if self._available is None:
            bgz = self._data_dir / _TX_FILE
            tbi = self._data_dir / f"{_TX_FILE}.tbi"
            self._available = bgz.exists() and tbi.exists()
            if self._available:
                logger.info("gnomAD tx_annotated data available at %s", self._data_dir)
            else:
                logger.info("gnomAD tx_annotated data not found at %s — disabled", self._data_dir)
        return self._available

    @property
    def is_loaded(self) -> bool:
        return self.available

    def _get_tabix(self):
        if self._tabix is None and self.available:
            import pysam
            self._tabix = pysam.TabixFile(str(self._data_dir / _TX_FILE))
        return self._tabix

    def close(self):
        if self._tabix is not None:
            self._tabix.close()
            self._tabix = None

    # ------------------------------------------------------------------
    # Core lookup
    # ------------------------------------------------------------------

    def _lookup_sync(
        self, chrom: str, pos: int, ref: str, alt: str,
    ) -> Optional[Dict[str, Any]]:
        tabix = self._get_tabix()
        if not tabix:
            return None

        chrom_clean = str(chrom).replace("chr", "")
        ref_upper = ref.upper()
        alt_upper = alt.upper()

        try:
            for row in tabix.fetch(chrom_clean, pos - 1, pos):
                fields = row.split("\t")
                if len(fields) < 5:
                    continue
                row_ref = fields[2].upper()
                row_alt = fields[3].upper()
                # Accept exact match OR strand-flipped alleles (consumer arrays sometimes
                # report alleles in the opposite orientation relative to the reference genome).
                if row_ref == ref_upper and row_alt == alt_upper:
                    return self._parse_tx_annotation(
                        fields[4], chrom_clean, pos, ref_upper, alt_upper,
                    )
                if row_ref == alt_upper and row_alt == ref_upper:
                    # Alleles are flipped — return data with canonical ref/alt from file
                    return self._parse_tx_annotation(
                        fields[4], chrom_clean, pos, row_ref, row_alt,
                    )
        except ValueError:
            # Contig not in file
            pass

        return None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_tx_annotation(
        json_str: str, chrom: str, pos: int, ref: str, alt: str,
    ) -> Dict[str, Any]:
        try:
            annotations = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return {"found": False, "source": "gnomad_tx"}

        if not annotations or not isinstance(annotations, list):
            return {"found": False, "source": "gnomad_tx"}

        transcripts = []
        primary_gene = None
        primary_csq = None
        primary_lof = None
        best_expr = float('-inf')

        for ann in annotations:
            entry: Dict[str, Any] = {
                "ensg": ann.get("ensg"),
                "symbol": ann.get("symbol"),
                "csq": ann.get("csq"),
                "lof": ann.get("lof"),
                "lof_flag": ann.get("lof_flag"),
            }

            # Parse mean_proportion
            mean_raw = ann.get("mean_proportion", "NaN")
            mean_prop = None
            if mean_raw not in (None, "NaN", "nan", ""):
                try:
                    mean_prop = float(mean_raw)
                except (ValueError, TypeError):
                    pass
            entry["mean_expression"] = mean_prop

            # Collect non-NaN tissue expression values
            tissues: Dict[str, float] = {}
            for key, val in ann.items():
                if key in _STANDARD_FIELDS:
                    continue
                if val not in (None, "NaN", "nan", ""):
                    try:
                        tissues[key] = round(float(val), 6)
                    except (ValueError, TypeError):
                        pass
            if tissues:
                # Store only top-10 tissues by expression to save space
                top = dict(sorted(tissues.items(), key=lambda x: x[1], reverse=True)[:10])
                entry["top_tissues"] = top
                entry["tissue_count"] = len(tissues)

            transcripts.append(entry)

            # Track primary transcript (highest mean expression, or first if all NaN)
            expr = mean_prop if mean_prop is not None else -1.0
            if primary_gene is None or expr > best_expr:
                best_expr = expr
                primary_gene = ann.get("symbol")
                primary_csq = ann.get("csq")
                primary_lof = ann.get("lof")

        result: Dict[str, Any] = {
            "found": True,
            "source": "gnomad_tx",
            "chrom": chrom,
            "pos": pos,
            "ref": ref,
            "alt": alt,
            "gene": primary_gene,
            "consequence": primary_csq,
            "lof": primary_lof,
            "transcript_count": len(transcripts),
            "transcripts": transcripts,
        }

        if best_expr >= 0:
            result["mean_expression"] = round(best_expr, 6)

        return result

    # ------------------------------------------------------------------
    # Async lookups
    # ------------------------------------------------------------------

    async def lookup(
        self, chrom: str, pos: int, ref: str, alt: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.available:
            return None
        return await asyncio.to_thread(self._lookup_sync, chrom, pos, ref, alt)

    async def lookup_batch(
        self, variants: List[Tuple[str, str, int, str, str]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup by position.

        Args:
            variants: list of (rsid, chrom, pos, ref, alt_csv) tuples.
                alt_csv may contain comma-separated alternatives.

        Returns: {rsid: result_or_none}
        """
        if not variants or not self.available:
            return {}
        return await asyncio.to_thread(self._lookup_batch_sync, variants)

    def _lookup_batch_sync(
        self, variants: List[Tuple[str, str, int, str, str]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        tabix = self._get_tabix()
        if not tabix:
            return {}

        results: Dict[str, Optional[Dict[str, Any]]] = {}

        for rsid, chrom, pos, ref, alt_csv in variants:
            chrom_clean = str(chrom).replace("chr", "")
            pos_int = int(pos)
            ref_upper = str(ref).upper()

            found = False
            for alt in str(alt_csv).split(","):
                alt = alt.strip().upper()
                if not alt:
                    continue
                hit = self._lookup_sync(chrom_clean, pos_int, ref_upper, alt)
                if hit and hit.get("found"):
                    hit["rsid"] = rsid
                    results[rsid] = hit
                    found = True
                    break

            if not found:
                results[rsid] = None

        return results


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_instance: Optional[GnomadTxService] = None


def get_gnomad_tx_service() -> GnomadTxService:
    global _instance
    if _instance is None:
        _instance = GnomadTxService()
    return _instance
