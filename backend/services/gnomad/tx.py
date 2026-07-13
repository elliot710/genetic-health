"""gnomAD transcript annotation + GTEx tissue-expression lookups.

Split out of gnomad_local.py; see the package __init__ for the public surface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.services.gnomad.cache import _GNOMAD_DATA_DIR

logger = logging.getLogger(__name__)


# GnomadTxService — transcript annotation + GTEx tissue expression
# (formerly gnomad_tx.py)
# ---------------------------------------------------------------------------

_TX_FILE = "all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz"

# Fields in the tx_annotation JSON that are NOT tissue names
_TX_STANDARD_FIELDS = frozenset({
    "ensg", "csq", "symbol", "lof", "lof_flag", "mean_proportion",
})


class GnomadTxService:
    """Lookup service for gnomAD transcript annotations with GTEx tissue expression.

    Uses pysam.TabixFile for O(log n) random-access lookups by genomic position.
    Data file: all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz
    """

    def __init__(self):
        self._data_dir = _GNOMAD_DATA_DIR
        self._tabix = None
        self._available: Optional[bool] = None

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
                if row_ref == ref_upper and row_alt == alt_upper:
                    return self._parse_tx_annotation(
                        fields[4], chrom_clean, pos, ref_upper, alt_upper,
                    )
                if row_ref == alt_upper and row_alt == ref_upper:
                    return self._parse_tx_annotation(
                        fields[4], chrom_clean, pos, row_ref, row_alt,
                    )
        except ValueError:
            pass

        return None

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

            mean_raw = ann.get("mean_proportion", "NaN")
            mean_prop = None
            if mean_raw not in (None, "NaN", "nan", ""):
                try:
                    mean_prop = float(mean_raw)
                except (ValueError, TypeError):
                    pass
            entry["mean_expression"] = mean_prop

            tissues: Dict[str, float] = {}
            for key, val in ann.items():
                if key in _TX_STANDARD_FIELDS:
                    continue
                if val not in (None, "NaN", "nan", ""):
                    try:
                        tissues[key] = round(float(val), 6)
                    except (ValueError, TypeError):
                        pass
            if tissues:
                top = dict(sorted(tissues.items(), key=lambda x: x[1], reverse=True)[:10])
                entry["top_tissues"] = top
                entry["tissue_count"] = len(tissues)

            transcripts.append(entry)

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

    async def lookup(
        self, chrom: str, pos: int, ref: str, alt: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.available:
            return None
        return await asyncio.to_thread(self._lookup_sync, chrom, pos, ref, alt)

    async def lookup_batch(
        self, variants: List[Tuple[str, str, int, str, str]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup. variants: list of (rsid, chrom, pos, ref, alt_csv) tuples."""
        if not variants or not self.available:
            return {}
        return await asyncio.to_thread(self._lookup_batch_sync, variants)

    def _lookup_batch_sync(
        self, variants: List[Tuple[str, str, int, str, str]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Bulk batch lookup using chromosome-range scans to avoid 609K random seeks.

        Groups variants by chromosome, sorts by position within each chromosome,
        then fetches a single range [min_pos, max_pos] per chromosome.  This reads
        the bgz file sequentially — dramatically faster than one tabix.fetch() per
        variant for large inputs.
        """
        import time as _time
        tabix = self._get_tabix()
        if not tabix:
            return {}

        # Group variants by chromosome.
        # by_chrom: chrom -> sorted list of (pos, rsid, ref_upper, alts_list)
        by_chrom: Dict[str, list] = {}
        for rsid, chrom, pos, ref, alt_csv in variants:
            chrom_clean = str(chrom).replace("chr", "")
            by_chrom.setdefault(chrom_clean, []).append(
                (int(pos), rsid, str(ref).upper(),
                 [a.strip().upper() for a in str(alt_csv).split(",") if a.strip()])
            )

        # Pre-initialise all results to None (not found)
        results: Dict[str, Optional[Dict[str, Any]]] = {
            rsid: None
            for _, rsid, _, _ in (item for items in by_chrom.values() for item in items)
        }

        # Define natural chromosome sort order
        def _chrom_key(c: str):
            c = c.replace("chr", "")
            if c.isdigit():
                return (0, int(c))
            return (1, c)

        found_count = 0
        processed = 0
        total = len(variants)
        t0 = _time.monotonic()

        for chrom_key_val, chrom_variants in sorted(by_chrom.items(), key=lambda x: _chrom_key(x[0])):
            chrom_variants.sort(key=lambda x: x[0])  # sort by pos

            # Build position index: pos -> list of (rsid, ref, alts)
            pos_index: Dict[int, list] = {}
            for pos, rsid, ref, alts in chrom_variants:
                pos_index.setdefault(pos, []).append((rsid, ref, alts))

            min_pos = chrom_variants[0][0]
            max_pos = chrom_variants[-1][0]

            try:
                for row in tabix.fetch(chrom_key_val, min_pos - 1, max_pos + 1):
                    fields = row.split("\t")
                    if len(fields) < 5:
                        continue
                    try:
                        row_pos = int(fields[1])
                    except (ValueError, IndexError):
                        continue
                    if row_pos not in pos_index:
                        continue
                    row_ref = fields[2].upper()
                    row_alt = fields[3].upper()
                    for rsid, ref, alts in pos_index[row_pos]:
                        if results.get(rsid) is not None and results[rsid] and results[rsid].get('found'):
                            continue  # already found
                        matched = False
                        for alt in alts:
                            if (row_ref == ref and row_alt == alt) or (row_ref == alt and row_alt == ref):
                                matched = True
                                break
                        if matched:
                            hit = self._parse_tx_annotation(
                                fields[4], chrom_key_val, row_pos, row_ref, row_alt,
                            )
                            if hit and hit.get("found"):
                                hit["rsid"] = rsid
                                results[rsid] = hit
                                found_count += 1
            except ValueError:
                pass

            processed += len(chrom_variants)
            elapsed = _time.monotonic() - t0
            logger.debug(
                "  gnomAD-tx chr%s: %d/%d processed, %d found (%.1fs)",
                chrom_key_val, processed, total, found_count, elapsed,
            )

        elapsed = _time.monotonic() - t0
        logger.info(
            "  gnomAD-tx complete: %d/%d found in %.1fs",
            found_count, total, elapsed,
        )
        return results


_gnomad_tx_instance: Optional[GnomadTxService] = None


def get_gnomad_tx_service() -> GnomadTxService:
    global _gnomad_tx_instance
    if _gnomad_tx_instance is None:
        _gnomad_tx_instance = GnomadTxService()
    return _gnomad_tx_instance
