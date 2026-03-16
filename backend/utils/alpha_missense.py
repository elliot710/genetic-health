"""
AlphaMissense data extraction utility.

Provides lookup of AlphaMissense pathogenicity predictions for genetic variants
from local pre-downloaded data files (no external API calls needed).

Data source: DeepMind AlphaMissense — "Accurate proteome-wide missense variant
effect prediction with AlphaMissense" (Cheng et al., Science 2023).

IMPORTANT: AlphaMissense predictions are computational (AI-based) and have NOT
been clinically validated. They should NOT be used as a substitute for
professional medical advice, diagnosis, or treatment.

License: Creative Commons Attribution 4.0 (CC-BY).

Expected files in DATA_DIR:
  - AlphaMissense_hg38.tsv.gz  (bgzip-compressed, tabix-indexed)
  - AlphaMissense_hg38.tsv.gz.tbi  (tabix index)
  - AlphaMissense_hg19.tsv.gz  (bgzip-compressed, tabix-indexed — hg19 coordinates)
  - AlphaMissense_hg19.tsv.gz.tbi  (tabix index)
  - AlphaMissense_isoforms_hg38.tsv.gz  (bgzip-compressed, tabix-indexed — per-isoform)
  - AlphaMissense_isoforms_hg38.tsv.gz.tbi  (tabix index)
  - AlphaMissense_gene_hg38.tsv.gz  (gene-level averages, gzip-compressed)
  - AlphaMissense_gene_hg19.tsv.gz  (gene-level averages, gzip-compressed — hg19 transcripts)
"""
import gzip
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default data directory — overridable via ALPHA_MISSENSE_DATA_DIR env var
DATA_DIR = Path(os.environ.get(
    "ALPHA_MISSENSE_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "alpha_missense"),
))

_VARIANT_HG38 = "AlphaMissense_hg38.tsv.gz"
_VARIANT_HG19 = "AlphaMissense_hg19.tsv.gz"
_ISOFORMS_HG38 = "AlphaMissense_isoforms_hg38.tsv.gz"
_GENE_HG38 = "AlphaMissense_gene_hg38.tsv.gz"
_GENE_HG19 = "AlphaMissense_gene_hg19.tsv.gz"


class AlphaMissenseService:
    """Lookup service for AlphaMissense pathogenicity predictions.

    Uses pysam.TabixFile for O(log n) random-access variant lookups against
    bgzip-sorted files (hg38, hg19, isoforms), and in-memory dicts for
    small gene-level data.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = Path(data_dir) if data_dir else DATA_DIR
        self._tabix_hg38 = None
        self._tabix_hg19 = None
        self._tabix_isoforms = None
        self._gene_map: Optional[Dict[str, float]] = None
        self._available: Optional[bool] = None
        self._hg19_available: Optional[bool] = None
        self._isoforms_available: Optional[bool] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _check_tabix_pair(self, filename: str) -> bool:
        """Check whether a bgzip + .tbi pair exist in the data directory."""
        return (
            (self._data_dir / filename).exists()
            and (self._data_dir / f"{filename}.tbi").exists()
        )

    @property
    def available(self) -> bool:
        """Check whether hg38 variant-level data file + index exist."""
        if self._available is None:
            self._available = self._check_tabix_pair(_VARIANT_HG38)
            if not self._available:
                logger.info(
                    "AlphaMissense hg38 data not found at %s — predictions disabled.",
                    self._data_dir,
                )
        return self._available

    @property
    def hg19_available(self) -> bool:
        """Check whether hg19 variant-level data file + index exist."""
        if self._hg19_available is None:
            self._hg19_available = self._check_tabix_pair(_VARIANT_HG19)
            if self._hg19_available:
                logger.info("AlphaMissense hg19 data available")
        return self._hg19_available

    @property
    def isoforms_available(self) -> bool:
        """Check whether isoform-level data file + index exist."""
        if self._isoforms_available is None:
            self._isoforms_available = self._check_tabix_pair(_ISOFORMS_HG38)
            if self._isoforms_available:
                logger.info("AlphaMissense isoforms data available")
        return self._isoforms_available

    def _open_tabix(self, filename: str):
        """Open a tabix file by filename."""
        import pysam
        path = str(self._data_dir / filename)
        return pysam.TabixFile(path)

    def _get_tabix_hg38(self):
        if self._tabix_hg38 is None and self.available:
            self._tabix_hg38 = self._open_tabix(_VARIANT_HG38)
        return self._tabix_hg38

    def _get_tabix_hg19(self):
        if self._tabix_hg19 is None and self.hg19_available:
            self._tabix_hg19 = self._open_tabix(_VARIANT_HG19)
        return self._tabix_hg19

    def _get_tabix_isoforms(self):
        if self._tabix_isoforms is None and self.isoforms_available:
            self._tabix_isoforms = self._open_tabix(_ISOFORMS_HG38)
        return self._tabix_isoforms

    def _load_gene_map(self) -> Dict[str, float]:
        """Load gene-level averages into memory from both hg38 and hg19 files."""
        if self._gene_map is not None:
            return self._gene_map

        self._gene_map = {}
        for gene_file in [_GENE_HG38, _GENE_HG19]:
            gene_path = self._data_dir / gene_file
            if not gene_path.exists():
                continue
            try:
                with gzip.open(gene_path, "rt") as fh:
                    for line in fh:
                        if line.startswith("#") or line.startswith("transcript_id"):
                            continue
                        parts = line.strip().split("\t")
                        if len(parts) >= 2:
                            transcript_id = parts[0]
                            try:
                                mean_score = float(parts[1])
                            except ValueError:
                                continue
                            self._gene_map[transcript_id] = mean_score
            except Exception as e:
                logger.error("Failed to load AlphaMissense gene data from %s: %s", gene_file, e)

        logger.info("Loaded %d AlphaMissense gene-level scores", len(self._gene_map))
        return self._gene_map

    def close(self):
        for tbx in (self._tabix_hg38, self._tabix_hg19, self._tabix_isoforms):
            if tbx is not None:
                tbx.close()
        self._tabix_hg38 = None
        self._tabix_hg19 = None
        self._tabix_isoforms = None

    # ------------------------------------------------------------------
    # Variant-level lookup
    # ------------------------------------------------------------------

    def _lookup_in_tabix(
        self,
        tabix,
        chrom: str,
        pos: int,
        ref: str,
        alt: str,
        has_uniprot: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Shared tabix lookup logic for both main and isoform files.

        Args:
            tabix: pysam.TabixFile
            chrom: Chromosome string, e.g. "chr1" or "1"
            pos: 1-based genomic position
            ref: Reference allele
            alt: Alternative allele
            has_uniprot: True for main hg38/hg19 files (10 columns),
                         False for isoforms file (9 columns, no uniprot_id)

        Returns:
            Dict with am_pathogenicity, am_class, etc. or None.
        """
        chrom_str = chrom if chrom.startswith("chr") else f"chr{chrom}"

        try:
            for row in tabix.fetch(chrom_str, pos - 1, pos):
                fields = row.split("\t")
                min_cols = 10 if has_uniprot else 9
                if len(fields) < min_cols - 1:
                    continue
                row_ref = fields[2]
                row_alt = fields[3]
                if row_ref == ref and row_alt == alt:
                    if has_uniprot:
                        # CHROM POS REF ALT genome uniprot_id transcript_id protein_variant am_pathogenicity am_class
                        try:
                            score = float(fields[8])
                        except (ValueError, IndexError):
                            continue
                        return {
                            "found": True,
                            "source": "alpha_missense",
                            "chrom": fields[0],
                            "pos": int(fields[1]),
                            "ref": row_ref,
                            "alt": row_alt,
                            "genome": fields[4],
                            "uniprot_id": fields[5],
                            "transcript_id": fields[6],
                            "protein_variant": fields[7],
                            "am_pathogenicity": score,
                            "am_class": fields[9] if len(fields) > 9 else None,
                        }
                    else:
                        # CHROM POS REF ALT genome transcript_id protein_variant am_pathogenicity am_class
                        try:
                            score = float(fields[7])
                        except (ValueError, IndexError):
                            continue
                        return {
                            "found": True,
                            "source": "alpha_missense",
                            "chrom": fields[0],
                            "pos": int(fields[1]),
                            "ref": row_ref,
                            "alt": row_alt,
                            "genome": fields[4],
                            "uniprot_id": None,
                            "transcript_id": fields[5],
                            "protein_variant": fields[6],
                            "am_pathogenicity": score,
                            "am_class": fields[8] if len(fields) > 8 else None,
                        }
        except ValueError:
            return None
        except Exception as e:
            logger.error("AlphaMissense lookup error for %s:%d %s>%s: %s", chrom_str, pos, ref, alt, e)
            return None
        return None

    def lookup_variant(
        self,
        chrom: str,
        pos: int,
        ref: str,
        alt: str,
        genome: str = "hg38",
    ) -> Optional[Dict[str, Any]]:
        """Look up a single variant by genomic coordinates.

        Args:
            chrom: Chromosome string, e.g. "chr1" or "1"
            pos: 1-based genomic position
            ref: Reference allele
            alt: Alternative allele (single nucleotide)
            genome: "hg38" (default) or "hg19"

        Returns:
            Dict with am_pathogenicity, am_class, protein_variant, etc.
            or None if not found / data unavailable.
        """
        if genome == "hg19":
            tabix = self._get_tabix_hg19()
        else:
            tabix = self._get_tabix_hg38()
        if tabix is None:
            return None
        return self._lookup_in_tabix(tabix, chrom, pos, ref, alt, has_uniprot=True)

    def lookup_isoforms(
        self,
        chrom: str,
        pos: int,
        ref: str,
        alt: str,
    ) -> List[Dict[str, Any]]:
        """Look up all isoform-level predictions for a variant (hg38).

        Returns a list of results — one per transcript/isoform.
        """
        tabix = self._get_tabix_isoforms()
        if tabix is None:
            return []

        chrom_str = chrom if chrom.startswith("chr") else f"chr{chrom}"
        results: List[Dict[str, Any]] = []
        try:
            for row in tabix.fetch(chrom_str, pos - 1, pos):
                fields = row.split("\t")
                if len(fields) < 8:
                    continue
                # CHROM POS REF ALT genome transcript_id protein_variant am_pathogenicity am_class
                if fields[2] == ref and fields[3] == alt:
                    try:
                        score = float(fields[7])
                    except (ValueError, IndexError):
                        continue
                    results.append({
                        "found": True,
                        "source": "alpha_missense",
                        "chrom": fields[0],
                        "pos": int(fields[1]),
                        "ref": fields[2],
                        "alt": fields[3],
                        "genome": fields[4],
                        "transcript_id": fields[5],
                        "protein_variant": fields[6],
                        "am_pathogenicity": score,
                        "am_class": fields[8] if len(fields) > 8 else None,
                    })
        except ValueError:
            pass
        except Exception as e:
            logger.error("AlphaMissense isoform lookup error for %s:%d %s>%s: %s", chrom_str, pos, ref, alt, e)
        return results

    def lookup_variants_batch(
        self,
        variants: List[Dict[str, Any]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup for multiple variants.

        Args:
            variants: List of dicts with keys: rsid, chromosome, position, ref_allele, alt_allele

        Returns:
            Dict mapping rsid → AlphaMissense result (or None).
        """
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        if not self.available:
            return results

        import time as _time
        total = len(variants)
        found_count = 0
        t0 = _time.monotonic()

        for idx, v in enumerate(variants):
            rsid = v.get("rsid", "")
            chrom = v.get("chromosome", "")
            pos = v.get("position")
            ref = v.get("ref_allele", "")
            alt = v.get("alt_allele", "")

            if not (chrom and pos and ref and alt):
                results[rsid] = None
                continue

            # Only single-nucleotide substitutions are missense candidates
            if len(ref) != 1 or len(alt) != 1:
                results[rsid] = None
                continue

            result = self.lookup_variant(chrom, int(pos), ref, alt)
            results[rsid] = result
            if result and result.get("found"):
                found_count += 1

            if (idx + 1) % 50000 == 0 or idx + 1 == total:
                elapsed = _time.monotonic() - t0
                rate = (idx + 1) / elapsed if elapsed > 0 else 0
                logger.info(
                    f"  AlphaMissense {idx + 1}/{total}: "
                    f"{found_count} found ({rate:.0f} variants/s, {elapsed:.1f}s elapsed)"
                )

        elapsed = _time.monotonic() - t0
        logger.info(f"  AlphaMissense complete: {found_count}/{total} found in {elapsed:.1f}s")
        return results

    # ------------------------------------------------------------------
    # Gene-level lookup
    # ------------------------------------------------------------------

    def lookup_gene(self, transcript_id: str) -> Optional[float]:
        """Get mean AlphaMissense pathogenicity for a transcript.

        Args:
            transcript_id: Ensembl transcript ID, e.g. "ENST00000335137.4"

        Returns:
            Mean pathogenicity score (0–1) or None.
        """
        gene_map = self._load_gene_map()

        # Try exact match first
        if transcript_id in gene_map:
            return gene_map[transcript_id]

        # Try without version suffix (ENST00000335137.4 → ENST00000335137)
        base_id = transcript_id.split(".")[0]
        for tid, score in gene_map.items():
            if tid.startswith(base_id):
                return score

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def classify_pathogenicity(score: float) -> str:
        """Apply official AlphaMissense classification thresholds.

        < 0.34  → likely_benign
        > 0.564 → likely_pathogenic
        else    → ambiguous
        """
        if score < 0.34:
            return "likely_benign"
        elif score > 0.564:
            return "likely_pathogenic"
        else:
            return "ambiguous"

    @staticmethod
    def format_result_for_display(
        result: Optional[Dict[str, Any]],
        isoforms: Optional[List[Dict[str, Any]]] = None,
        gene_score: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Format a lookup result for API/frontend consumption.

        Adds human-readable label, isoform data, gene-level score, and disclaimer.
        """
        if not result or not result.get("found"):
            return None

        score = result["am_pathogenicity"]
        am_class = result.get("am_class") or AlphaMissenseService.classify_pathogenicity(score)

        out: Dict[str, Any] = {
            "found": True,
            "source": "alpha_missense",
            "am_pathogenicity": score,
            "am_class": am_class,
            "protein_variant": result.get("protein_variant"),
            "uniprot_id": result.get("uniprot_id"),
            "transcript_id": result.get("transcript_id"),
            "disclaimer": (
                "AlphaMissense is an AI-based prediction and has not been "
                "clinically validated. It is not a substitute for professional "
                "medical advice."
            ),
        }

        if gene_score is not None:
            out["gene_mean_pathogenicity"] = round(gene_score, 4)

        if isoforms:
            out["isoforms"] = [
                {
                    "transcript_id": iso.get("transcript_id"),
                    "protein_variant": iso.get("protein_variant"),
                    "am_pathogenicity": iso.get("am_pathogenicity"),
                    "am_class": iso.get("am_class") or AlphaMissenseService.classify_pathogenicity(iso["am_pathogenicity"]),
                }
                for iso in isoforms
            ]
            out["isoform_count"] = len(isoforms)

        return out

    def lookup_comprehensive(
        self,
        chrom: str,
        pos: int,
        ref: str,
        alt: str,
        genome: str = "hg38",
        transcript_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Full lookup combining variant, isoforms, and gene-level data.

        Returns a formatted result dict ready for the API/frontend.
        """
        result = self.lookup_variant(chrom, pos, ref, alt, genome=genome)
        if not result:
            return None

        isoforms = self.lookup_isoforms(chrom, pos, ref, alt) if genome == "hg38" else []

        gene_score = None
        tid = transcript_id or result.get("transcript_id")
        if tid:
            gene_score = self.lookup_gene(tid)

        return self.format_result_for_display(result, isoforms=isoforms, gene_score=gene_score)


# ------------------------------------------------------------------
# Module-level singleton for reuse across the application
# ------------------------------------------------------------------

_service: Optional[AlphaMissenseService] = None


def get_alpha_missense_service() -> AlphaMissenseService:
    """Get or create the module-level AlphaMissenseService singleton."""
    global _service
    if _service is None:
        _service = AlphaMissenseService()
    return _service
