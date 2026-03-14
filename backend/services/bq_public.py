"""
BigQuery public dataset lookups — ChEMBL, FDA Drug, AlphaFold.

Results are cached in shared_variant_annotations JSON columns
(chembl_data, fda_drug_data, alphafold_data) so each BigQuery query
is only executed once per variant.

Datasets:
  - ebi_chembl (v33): drug mechanisms, indications, warnings, targets
  - fda_drug: drug labels with CYP/pharmacogenomic interaction info
  - deepmind_alphafold: protein structure confidence per gene

All SQL uses parameterized queries to prevent injection.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class BigQueryPublicService:
    """Query ChEMBL, FDA Drug, and AlphaFold via BigQuery public datasets."""

    def __init__(self):
        self._client = None
        self._available: Optional[bool] = None
        # Per-gene result cache — avoids re-querying BigQuery for variants
        # that share the same gene during a single analysis run.
        self._gene_cache: Dict[str, Dict[str, Any]] = {}

    def clear_gene_cache(self):
        """Clear the per-gene cache (call between analysis runs)."""
        self._gene_cache.clear()

    async def _ensure_client(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from google.cloud import bigquery
            logger.info("BQ public: initializing BigQuery client...")
            self._client = await asyncio.to_thread(bigquery.Client)
            self._available = True
            logger.info("BQ public: client initialized successfully")
        except Exception as e:
            logger.info("BigQuery public datasets unavailable: %s", e)
            self._available = False
        return self._available

    async def _query(
        self, sql: str, params: list | None = None, max_gb: int = 2
    ) -> List[Dict[str, Any]]:
        """Execute a parameterized BigQuery query with byte budget."""
        if not await self._ensure_client():
            return []
        from google.cloud import bigquery
        import time as _time
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=max_gb * 1024**3,
        )
        if params:
            job_config.query_parameters = params
        try:
            t0 = _time.monotonic()
            result = await asyncio.to_thread(
                self._client.query, sql, job_config=job_config
            )
            rows = await asyncio.to_thread(lambda: list(result))
            elapsed = _time.monotonic() - t0
            logger.info("BQ query returned %d rows in %.1fs", len(rows), elapsed)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("BigQuery query failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Main entry point for annotation caching
    # ------------------------------------------------------------------

    async def enrich_variant(
        self,
        gene_symbol: str,
        enabled_sources: Set[str],
    ) -> Dict[str, Any]:
        """Fetch ChEMBL / FDA / AlphaFold data for a gene.

        Returns ``{source_name: data_dict}`` only for sources in
        *enabled_sources* that yield results.
        Uses per-gene caching so the same gene is only queried once.
        """
        bq_sources = {"chembl", "fda_drug", "alphafold"}
        requested = bq_sources & enabled_sources
        if not requested:
            return {}

        cache_key = gene_symbol.upper()
        if cache_key in self._gene_cache:
            cached = self._gene_cache[cache_key]
            return {k: v for k, v in cached.items() if k in requested}

        result: Dict[str, Any] = {}

        if "chembl" in enabled_sources:
            result["chembl"] = await self.lookup_gene_drugs(gene_symbol)

        if "fda_drug" in enabled_sources:
            # Use ChEMBL drug names (if available) for FDA label lookups
            drug_names: List[str] = []
            cd = result.get("chembl") or {}
            if cd.get("found"):
                drug_names = [
                    d["drug_name"]
                    for d in cd.get("drugs", [])
                    if d.get("drug_name")
                ]
            result["fda_drug"] = await self._lookup_fda_for_gene(
                gene_symbol, drug_names
            )

        if "alphafold" in enabled_sources:
            result["alphafold"] = await self.lookup_alphafold_gene(gene_symbol)

        self._gene_cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # ChEMBL: Gene -> Drug lookups
    # ------------------------------------------------------------------

    async def lookup_gene_drugs(self, gene_symbol: str) -> Dict[str, Any]:
        """Find drugs targeting a gene via ChEMBL mechanisms + target components."""
        from google.cloud import bigquery as bq

        gene_upper = gene_symbol.upper()
        gene_pattern = f"%{gene_upper}%"

        # Step 1: targets for this gene (match gene symbol in synonyms,
        # protein description, or target preferred name)
        rows = await self._query(
            """
            SELECT DISTINCT td.tid, td.pref_name AS target_name,
                   cs.accession AS uniprot_id
            FROM `bigquery-public-data.ebi_chembl.component_sequences_33` cs
            JOIN `bigquery-public-data.ebi_chembl.target_components_33` tc
                 ON cs.component_id = tc.component_id
            JOIN `bigquery-public-data.ebi_chembl.target_dictionary_33` td
                 ON tc.tid = td.tid
            LEFT JOIN `bigquery-public-data.ebi_chembl.component_synonyms_33` csyn
                 ON cs.component_id = csyn.component_id
            WHERE cs.organism = 'Homo sapiens'
              AND (UPPER(cs.description) LIKE @pat
                   OR UPPER(td.pref_name) LIKE @pat
                   OR UPPER(csyn.component_synonym) = @gene)
            LIMIT 20
            """,
            params=[
                bq.ScalarQueryParameter("pat", "STRING", gene_pattern),
                bq.ScalarQueryParameter("gene", "STRING", gene_upper),
            ],
        )

        if not rows:
            return {"gene": gene_symbol, "found": False, "drugs": [], "warnings": []}

        tids = [r["tid"] for r in rows]
        targets = {r["tid"]: r for r in rows}

        # Step 2: drug mechanisms for those targets
        # tid is INT64 in target_dictionary but compared via parameterized array
        drugs = await self._query(
            """
            SELECT DISTINCT
                md.pref_name AS drug_name, md.chembl_id, md.max_phase,
                md.first_approval, dm.mechanism_of_action, dm.action_type, dm.tid
            FROM `bigquery-public-data.ebi_chembl.drug_mechanism_33` dm
            JOIN `bigquery-public-data.ebi_chembl.molecule_dictionary_33` md
                 ON dm.molregno = md.molregno
            WHERE dm.tid IN UNNEST(@tids) AND md.pref_name IS NOT NULL
            LIMIT 50
            """,
            params=[bq.ArrayQueryParameter("tids", "INT64", [int(t) for t in tids])],
        )

        for d in drugs:
            tid = d.pop("tid", None)
            if tid and tid in targets:
                d["target_name"] = targets[tid]["target_name"]
                d["uniprot_id"] = targets[tid].get("uniprot_id")

        # Step 3: warnings for those drugs
        chembl_ids = [d["chembl_id"] for d in drugs if d.get("chembl_id")]
        warnings: list = []
        if chembl_ids:
            mol_rows = await self._query(
                """
                SELECT molregno, chembl_id
                FROM `bigquery-public-data.ebi_chembl.molecule_dictionary_33`
                WHERE chembl_id IN UNNEST(@ids)
                """,
                params=[bq.ArrayQueryParameter("ids", "STRING", chembl_ids)],
            )
            molregnos = [r["molregno"] for r in mol_rows]
            if molregnos:
                warnings = await self._query(
                    """
                    SELECT DISTINCT md.pref_name AS drug_name,
                           dw.warning_type, dw.warning_class,
                           dw.warning_description, dw.warning_year
                    FROM `bigquery-public-data.ebi_chembl.drug_warning_33` dw
                    JOIN `bigquery-public-data.ebi_chembl.molecule_dictionary_33` md
                         ON dw.molregno = md.molregno
                    WHERE dw.molregno IN UNNEST(@mrn)
                      AND dw.warning_description IS NOT NULL
                    LIMIT 20
                    """,
                    params=[bq.ArrayQueryParameter("mrn", "INT64", molregnos)],
                )

        return {
            "gene": gene_symbol,
            "found": True,
            "source": "chembl_bigquery",
            "targets": list(targets.values()),
            "drugs": drugs,
            "warnings": warnings,
        }

    async def lookup_drug_info(self, drug_name: str) -> Dict[str, Any]:
        """Look up a drug by name in ChEMBL."""
        from google.cloud import bigquery as bq

        rows = await self._query(
            """
            SELECT md.pref_name AS drug_name, md.chembl_id, md.max_phase,
                   md.first_approval, md.molecule_type, md.oral, md.parenteral
            FROM `bigquery-public-data.ebi_chembl.molecule_dictionary_33` md
            WHERE UPPER(md.pref_name) = @name
            LIMIT 1
            """,
            params=[bq.ScalarQueryParameter("name", "STRING", drug_name.upper())],
        )
        if not rows:
            return {"drug": drug_name, "found": False}

        drug = rows[0]

        mol_rows = await self._query(
            """
            SELECT molregno
            FROM `bigquery-public-data.ebi_chembl.molecule_dictionary_33`
            WHERE chembl_id = @cid
            """,
            params=[bq.ScalarQueryParameter("cid", "STRING", drug["chembl_id"])],
        )
        if not mol_rows:
            return {"drug": drug_name, "found": True, **drug}
        molregno = mol_rows[0]["molregno"]

        mechanisms = await self._query(
            """
            SELECT dm.mechanism_of_action, dm.action_type,
                   td.pref_name AS target_name
            FROM `bigquery-public-data.ebi_chembl.drug_mechanism_33` dm
            LEFT JOIN `bigquery-public-data.ebi_chembl.target_dictionary_33` td
                      ON dm.tid = td.tid
            WHERE dm.molregno = @mrn
            """,
            params=[bq.ScalarQueryParameter("mrn", "INT64", molregno)],
        )
        indications = await self._query(
            """
            SELECT mesh_heading, efo_term, max_phase_for_ind
            FROM `bigquery-public-data.ebi_chembl.drug_indication_33`
            WHERE molregno = @mrn
            """,
            params=[bq.ScalarQueryParameter("mrn", "INT64", molregno)],
        )
        warnings = await self._query(
            """
            SELECT warning_type, warning_class, warning_description, warning_year
            FROM `bigquery-public-data.ebi_chembl.drug_warning_33`
            WHERE molregno = @mrn AND warning_description IS NOT NULL
            """,
            params=[bq.ScalarQueryParameter("mrn", "INT64", molregno)],
        )

        return {
            "drug": drug_name,
            "found": True,
            "source": "chembl_bigquery",
            **drug,
            "mechanisms": mechanisms,
            "indications": indications,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # FDA Drug: CYP enzyme interaction lookups
    # ------------------------------------------------------------------

    async def _lookup_fda_for_gene(
        self, gene_symbol: str, drug_names: List[str]
    ) -> Dict[str, Any]:
        """Look up FDA drug labels for a gene's known drugs."""
        from google.cloud import bigquery as bq

        labels: list = []
        for name in drug_names[:5]:
            pattern = f"%{name.upper()}%"
            rows = await self._query(
                """
                SELECT openfda_generic_name, openfda_brand_name,
                       openfda_route, drug_interactions
                FROM `bigquery-public-data.fda_drug.drug_label`
                WHERE UPPER(openfda_generic_name) LIKE @pat
                   OR UPPER(openfda_brand_name) LIKE @pat
                LIMIT 1
                """,
                params=[bq.ScalarQueryParameter("pat", "STRING", pattern)],
            )
            if rows:
                row = rows[0]
                labels.append({
                    "generic_name": row.get("openfda_generic_name"),
                    "brand_name": row.get("openfda_brand_name"),
                    "route": row.get("openfda_route"),
                    "cyp_enzymes": self._extract_cyp_mentions(
                        row.get("drug_interactions") or ""
                    ),
                    "drug_interactions": self._truncate(
                        row.get("drug_interactions"), 1000
                    ),
                })

        if not labels:
            return {"gene": gene_symbol, "found": False}
        return {
            "gene": gene_symbol,
            "found": True,
            "source": "fda_drug_bigquery",
            "labels": labels,
        }

    async def lookup_fda_drug_interactions(self, drug_name: str) -> Dict[str, Any]:
        """Look up FDA drug label for CYP/pharmacogenomic interaction info."""
        from google.cloud import bigquery as bq

        pattern = f"%{drug_name.upper()}%"
        rows = await self._query(
            """
            SELECT openfda_generic_name, openfda_brand_name,
                   openfda_pharm_class_moa, openfda_pharm_class_epc,
                   openfda_substance_name, openfda_route,
                   drug_interactions, indications_and_usage, pharmacokinetics
            FROM `bigquery-public-data.fda_drug.drug_label`
            WHERE UPPER(openfda_generic_name) LIKE @pat
               OR UPPER(openfda_brand_name) LIKE @pat
            LIMIT 3
            """,
            params=[bq.ScalarQueryParameter("pat", "STRING", pattern)],
        )
        if not rows:
            return {"drug": drug_name, "found": False}

        label = rows[0]
        return {
            "drug": drug_name,
            "found": True,
            "source": "fda_drug_bigquery",
            "generic_name": label.get("openfda_generic_name"),
            "brand_name": label.get("openfda_brand_name"),
            "pharm_class": label.get("openfda_pharm_class_moa"),
            "route": label.get("openfda_route"),
            "cyp_enzymes_mentioned": self._extract_cyp_mentions(
                label.get("drug_interactions") or ""
            ),
            "drug_interactions": self._truncate(
                label.get("drug_interactions"), 1000
            ),
            "indications": self._truncate(
                label.get("indications_and_usage"), 500
            ),
            "pharmacokinetics": self._truncate(
                label.get("pharmacokinetics"), 500
            ),
        }

    async def lookup_fda_cyp_drugs(self, cyp_enzyme: str) -> List[Dict[str, Any]]:
        """Find all FDA drugs that mention a specific CYP enzyme."""
        from google.cloud import bigquery as bq

        pattern = f"%{cyp_enzyme.lower()}%"
        return await self._query(
            """
            SELECT DISTINCT openfda_generic_name, openfda_brand_name,
                   openfda_pharm_class_moa, openfda_route
            FROM `bigquery-public-data.fda_drug.drug_label`
            WHERE LOWER(drug_interactions) LIKE @pat
              AND openfda_generic_name IS NOT NULL
            ORDER BY openfda_generic_name
            LIMIT 50
            """,
            params=[bq.ScalarQueryParameter("pat", "STRING", pattern)],
        )

    # ------------------------------------------------------------------
    # AlphaFold: gene -> protein structure confidence
    # ------------------------------------------------------------------

    async def lookup_alphafold_gene(self, gene_symbol: str) -> Dict[str, Any]:
        """Look up AlphaFold protein structure prediction confidence."""
        from google.cloud import bigquery as bq

        rows = await self._query(
            """
            SELECT entryId, gene, uniprotAccession, uniprotId,
                   proteinFullNames, organismScientificName,
                   globalMetricValue,
                   fractionPlddtVeryHigh, fractionPlddtConfident,
                   fractionPlddtLow, fractionPlddtVeryLow,
                   modelCreatedDate, isReviewed
            FROM `bigquery-public-data.deepmind_alphafold.metadata`
            WHERE UPPER(gene) = @gene
              AND organismScientificName = 'Homo sapiens'
              AND isReviewed = TRUE
            ORDER BY globalMetricValue DESC
            LIMIT 5
            """,
            params=[
                bq.ScalarQueryParameter("gene", "STRING", gene_symbol.upper()),
            ],
            max_gb=130,
        )

        if not rows:
            return {"gene": gene_symbol, "found": False}

        best = rows[0]
        return {
            "gene": gene_symbol,
            "found": True,
            "source": "alphafold_bigquery",
            "entry_id": best.get("entryId"),
            "uniprot_id": best.get("uniprotAccession"),
            "protein_name": best.get("proteinFullNames"),
            "global_confidence": best.get("globalMetricValue"),
            "plddt_very_high": best.get("fractionPlddtVeryHigh"),
            "plddt_confident": best.get("fractionPlddtConfident"),
            "plddt_low": best.get("fractionPlddtLow"),
            "plddt_very_low": best.get("fractionPlddtVeryLow"),
            "model_date": str(best.get("modelCreatedDate") or ""),
            "all_isoforms": [
                {
                    "entry_id": r.get("entryId"),
                    "uniprot_id": r.get("uniprotAccession"),
                    "confidence": r.get("globalMetricValue"),
                }
                for r in rows
            ],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_cyp_mentions(text: str) -> List[str]:
        """Extract CYP enzyme names from text."""
        if not text:
            return []
        matches = re.findall(r"CYP\s*\d[A-Z]\d+", text, re.IGNORECASE)
        seen: set = set()
        result: list = []
        for m in matches:
            norm = m.upper().replace(" ", "")
            if norm not in seen:
                seen.add(norm)
                result.append(norm)
        return sorted(result)

    @staticmethod
    def _truncate(text: Optional[str], max_len: int) -> Optional[str]:
        if not text or len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    async def close(self):
        if self._client:
            try:
                await asyncio.to_thread(self._client.close)
            except Exception:
                pass
            self._client = None


# Singleton
_instance: Optional[BigQueryPublicService] = None


def get_bq_public_service() -> BigQueryPublicService:
    global _instance
    if _instance is None:
        _instance = BigQueryPublicService()
    return _instance
