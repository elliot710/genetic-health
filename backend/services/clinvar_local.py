"""
Local ClinVar database for fast variant lookups without API calls.

Uses NCBI ClinVar data from two formats:
  TSV (tsv/) — 11 files providing rich rsid→annotation data
  VCF (vcf/) — allele frequencies, molecular consequences,
                oncogenicity, somatic clinical impact

Directory structure expected:
  <CLINVAR_DATA_DIR>/
    tsv/
      variant_summary.txt.gz        (REQUIRED — main rsid index)
      var_citations.txt              (allele→PubMed citations)
      gene_condition_source_id.txt   (gene→disease associations)
      cross_references.txt           (allele→external DB cross-refs)
      disease_names.txt              (concept_id→disease details)
      gene_specific_summary.txt      (gene-level ClinVar stats)
      hgvs4variation.txt.gz          (HGVS nomenclature per allele)
      allele_gene.txt.gz             (allele→gene detail mapping)
      submission_summary.txt.gz      (submission count per variation)
      summary_of_conflicting_interpretations.txt (conflict flags)
      variation_allele.txt.gz        (variation→allele linking)
    vcf/
      clinvar.vcf.gz                 (allele freqs, mol. consequences, oncogenicity)

Usage:
    svc = get_clinvar_local_service()
    await svc.ensure_loaded()
    result = svc.lookup("rs1234")
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger(__name__)

_CLINVAR_DATA_DIR = Path(os.environ.get(
    "CLINVAR_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "clinvar"),
))

# External DB cross-references worth keeping
_XREF_DBS_OF_INTEREST = frozenset({
    "OMIM", "UniProtKB", "ClinGen", "MedGen", "Orphanet", "GeneReviews",
    "GTR", "dbSNP", "dbVar", "PharmGKB",
})

# Frequently repeated strings — intern for memory savings
_intern = sys.intern

# Named-tuple-like indices for compact TSV entry storage (saves ~60% vs dicts)
# variant_summary entry tuple positions:
_E_AID, _E_VID, _E_TYPE, _E_SIG, _E_COND = 0, 1, 2, 3, 4
_E_PHIDS, _E_RCV, _E_GENE, _E_GID, _E_ORIGIN = 5, 6, 7, 8, 9
_E_ASM, _E_REV, _E_CHR, _E_START, _E_STOP = 10, 11, 12, 13, 14

# VCF entry tuple positions:
_V_AID, _V_SIG, _V_COND, _V_REV, _V_HGVS, _V_GENE = 0, 1, 2, 3, 4, 5
_V_MC, _V_EXAC, _V_TGP, _V_ESP = 6, 7, 8, 9
_V_ONC, _V_ONCREV, _V_SCI, _V_SIGCONF = 10, 11, 12, 13
_V_VCTYPE, _V_ORIGIN, _V_CLNVI, _V_DBVAR = 14, 15, 16, 17


class ClinVarLocalService:
    """In-memory rsid→ClinVar index built from local TSV + VCF files."""

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = Path(data_dir) if data_dir else _CLINVAR_DATA_DIR
        self._tsv_dir = self._data_dir / "tsv"
        self._vcf_dir = self._data_dir / "vcf"

        # --- Core indices ---
        self._index: Dict[str, List[tuple]] = {}       # rsid → [TSV entry tuples]
        self._vcf_index: Dict[str, List[tuple]] = {}   # rsid → [VCF entry tuples]

        # --- Supplementary TSV indices (tuples for memory efficiency) ---
        self._citations: Dict[str, List[str]] = {}         # allele_id → [pubmed_ids]
        self._gene_conditions: Dict[str, List[tuple]] = {} # gene → [(disease, source, source_id, mim)]
        self._cross_refs: Dict[str, List[tuple]] = {}      # allele_id → [(database, id)]
        self._diseases: Dict[str, tuple] = {}               # concept_id → (name, source, cid, sid, mim, cat)
        self._gene_stats: Dict[str, tuple] = {}             # gene → (gid, tot_sub, tot_al, plp, mim, unc, conf)
        self._hgvs: Dict[str, tuple] = {}                   # allele_id → (nuc, nuc_ch, prot, prot_ch, type, asm)
        self._allele_genes: Dict[str, tuple] = {}            # allele_id → (symbol, name, gid, category)
        self._submission_counts: Dict[str, int] = {}         # variation_id → count
        self._conflicting_variations: Set[str] = set()       # set of variation_ids
        self._variation_alleles: Dict[str, List[str]] = {}   # variation_id → [allele_ids]

        self._loaded = False
        self._load_lock = asyncio.Lock()
        self._files_loaded: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return (self._tsv_dir / "variant_summary.txt.gz").exists()

    @property
    def vcf_available(self) -> bool:
        return (self._vcf_dir / "clinvar.vcf.gz").exists()

    async def ensure_loaded(self) -> bool:
        """Load all ClinVar data files into memory. Returns True on success."""
        if self._loaded:
            return True
        async with self._load_lock:
            if self._loaded:
                return True
            if not self.available:
                logger.warning("ClinVar local: variant_summary.txt.gz not at %s", self._tsv_dir)
                return False
            try:
                total_start = time.time()

                # Phase 1: Core indices in parallel (TSV + VCF)
                core = [asyncio.to_thread(self._build_tsv_index)]
                if self.vcf_available:
                    core.append(asyncio.to_thread(self._build_vcf_index))
                await asyncio.gather(*core)

                # Phase 2: Supplementary TSV files in parallel
                loaders = [
                    self._load_citations,
                    self._load_gene_conditions,
                    self._load_cross_references,
                    self._load_disease_names,
                    self._load_gene_stats,
                    self._load_hgvs,
                    self._load_allele_genes,
                    self._load_submission_counts,
                    self._load_conflicting_interpretations,
                    self._load_variation_alleles,
                ]
                await asyncio.gather(*(asyncio.to_thread(fn) for fn in loaders))

                elapsed = time.time() - total_start
                logger.info(
                    "ClinVar local fully loaded in %.1fs — %d rsids (TSV), %d rsids (VCF), files: %s",
                    elapsed, len(self._index), len(self._vcf_index),
                    ", ".join(self._files_loaded),
                )
                self._loaded = True
                return True
            except Exception:
                logger.exception("ClinVar local DB failed to load")
                return False

    def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up a single rsid. Returns comprehensive ClinVar annotation or None."""
        if not self._loaded:
            return None

        tsv_entries = self._index.get(rsid)
        vcf_entries = self._vcf_index.get(rsid)

        if not tsv_entries and not vcf_entries:
            return {"found": False, "source": "clinvar_local"}

        clinical_sigs: List[str] = []
        conditions: List[str] = []
        genes: List[str] = []
        variation_ids: Set[str] = set()
        allele_ids: Set[str] = set()
        result_entries: List[Dict[str, Any]] = []

        # --- TSV entries (primary structured data) ---
        if tsv_entries:
            for e in tsv_entries:
                sig = e[_E_SIG]
                if sig and sig not in clinical_sigs:
                    clinical_sigs.append(sig)
                cond = e[_E_COND]
                if cond and cond not in conditions and cond != "not provided":
                    conditions.append(cond)
                gene = e[_E_GENE]
                if gene and gene not in genes:
                    genes.append(gene)
                vid = e[_E_VID]
                if vid:
                    variation_ids.add(vid)
                aid = e[_E_AID]
                if aid:
                    allele_ids.add(aid)

                hgvs = self._hgvs.get(aid)
                ag = self._allele_genes.get(aid)

                result_entries.append({
                    "uid": vid,
                    "allele_id": aid,
                    "title": f"{rsid} - {cond}" if cond else rsid,
                    "accession": e[_E_RCV],
                    "clinical_significance": [sig] if sig else [],
                    "conditions": [cond] if cond and cond != "not provided" else [],
                    "variation_type": e[_E_TYPE],
                    "gene": gene,
                    "gene_name": ag[1] if ag else "",
                    "review_status": e[_E_REV],
                    "origin": e[_E_ORIGIN],
                    "chromosome": e[_E_CHR],
                    "start": e[_E_START],
                    "stop": e[_E_STOP],
                    "hgvs_nucleotide": hgvs[0] if hgvs else "",
                    "hgvs_protein": hgvs[2] if hgvs else "",
                })

        # --- VCF entries (allele freqs, mol consequence, oncology) ---
        vcf_data: Optional[Dict[str, Any]] = None
        if vcf_entries:
            allele_freqs: Dict[str, float] = {}
            mol_consequences: List[str] = []
            oncogenicity: List[str] = []
            somatic_impact: List[str] = []
            conflicting_text: List[str] = []
            clinical_sources: List[str] = []

            for v in vcf_entries:
                v_aid = v[_V_AID]
                if v_aid:
                    allele_ids.add(v_aid)

                v_sig = v[_V_SIG]
                if v_sig and v_sig not in clinical_sigs:
                    clinical_sigs.append(v_sig)

                v_cond = v[_V_COND]
                if v_cond and v_cond != "not_specified" and v_cond != "not_provided":
                    cleaned = v_cond.replace("_", " ")
                    if cleaned not in conditions:
                        conditions.append(cleaned)

                v_gene = v[_V_GENE]
                if v_gene:
                    for gpart in v_gene.split("|"):
                        gsym = gpart.split(":")[0] if ":" in gpart else gpart
                        if gsym and gsym not in genes:
                            genes.append(gsym)

                mc = v[_V_MC]
                if mc and mc not in mol_consequences:
                    mol_consequences.append(mc)

                if v[_V_EXAC] is not None and "exac" not in allele_freqs:
                    allele_freqs["exac"] = v[_V_EXAC]
                if v[_V_TGP] is not None and "tgp" not in allele_freqs:
                    allele_freqs["tgp"] = v[_V_TGP]
                if v[_V_ESP] is not None and "esp" not in allele_freqs:
                    allele_freqs["esp"] = v[_V_ESP]

                onc = v[_V_ONC]
                if onc and onc not in oncogenicity:
                    oncogenicity.append(onc)
                sci = v[_V_SCI]
                if sci and sci not in somatic_impact:
                    somatic_impact.append(sci)
                conf = v[_V_SIGCONF]
                if conf and conf not in conflicting_text:
                    conflicting_text.append(conf)
                clnvi = v[_V_CLNVI]
                if clnvi:
                    clinical_sources.append(clnvi)

            vcf_data = {}
            if allele_freqs:
                vcf_data["allele_frequencies"] = allele_freqs
            if mol_consequences:
                vcf_data["molecular_consequences"] = mol_consequences[:10]
            if oncogenicity:
                vcf_data["oncogenicity"] = oncogenicity
            if somatic_impact:
                vcf_data["somatic_clinical_impact"] = somatic_impact
            if conflicting_text:
                vcf_data["conflicting_classifications"] = conflicting_text[:5]
            if clinical_sources:
                vcf_data["clinical_sources"] = clinical_sources[:10]

        # --- Enrich from supplementary TSV ---
        pmids: List[str] = []
        for aid in allele_ids:
            pmids.extend(self._citations.get(aid, ()))
        pmids = list(dict.fromkeys(pmids))[:50]

        cross_refs: List[Dict[str, str]] = []
        seen_xrefs: Set[str] = set()
        for aid in allele_ids:
            for xr in self._cross_refs.get(aid, ()):
                key = f"{xr[0]}:{xr[1]}"
                if key not in seen_xrefs:
                    seen_xrefs.add(key)
                    cross_refs.append({"database": xr[0], "id": xr[1]})
        cross_refs = cross_refs[:30]

        gene_conditions: List[Dict[str, str]] = []
        for gene in genes:
            for gc in self._gene_conditions.get(gene, ()):
                gene_conditions.append({
                    "disease": gc[0], "source": gc[1],
                    "source_id": gc[2], "disease_mim": gc[3],
                })
        gene_conditions = gene_conditions[:20]

        gene_stats_list: List[Dict[str, Any]] = []
        for gene in genes:
            gs = self._gene_stats.get(gene)
            if gs:
                gene_stats_list.append({
                    "gene": gene, "gene_id": gs[0],
                    "total_submissions": gs[1], "total_alleles": gs[2],
                    "pathogenic_likely_pathogenic": gs[3], "gene_mim": gs[4],
                    "uncertain": gs[5], "with_conflicts": gs[6],
                })

        has_conflicts = any(vid in self._conflicting_variations for vid in variation_ids)
        total_submissions = sum(self._submission_counts.get(vid, 0) for vid in variation_ids)

        disease_details: List[Dict[str, str]] = []
        seen_diseases: Set[str] = set()
        if tsv_entries:
            for e in tsv_entries:
                phids = e[_E_PHIDS]
                if phids:
                    for pid in phids.split(","):
                        pid = pid.strip()
                        if pid and pid not in seen_diseases:
                            dd = self._diseases.get(pid)
                            if dd:
                                seen_diseases.add(pid)
                                disease_details.append({
                                    "name": dd[0], "source": dd[1],
                                    "concept_id": dd[2], "source_id": dd[3],
                                    "disease_mim": dd[4], "category": dd[5],
                                })
        disease_details = disease_details[:10]

        review_statuses = list({e[_E_REV] for e in (tsv_entries or [])} - {""})

        result: Dict[str, Any] = {
            "found": True,
            "source": "clinvar_local",
            "count": len(tsv_entries or []) + len(vcf_entries or []),
            "ids": list(variation_ids)[:20],
            "allele_ids": list(allele_ids)[:20],
            "clinical_significances": clinical_sigs,
            "conditions": conditions,
            "genes": genes,
            "review_statuses": review_statuses,
            "has_conflicting_interpretations": has_conflicts,
            "total_submissions": total_submissions,
            "pubmed_ids": pmids,
            "cross_references": cross_refs,
            "gene_conditions": gene_conditions,
            "gene_stats": gene_stats_list,
            "disease_details": disease_details,
            "entries": result_entries[:10],
        }

        if vcf_data:
            result["vcf_data"] = vcf_data

        return result

    def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        return {rsid: self.lookup(rsid) for rsid in rsids}

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def variant_count(self) -> int:
        return len(self._index)

    @property
    def vcf_variant_count(self) -> int:
        return len(self._vcf_index)

    @property
    def files_loaded(self) -> List[str]:
        return list(self._files_loaded)

    # ------------------------------------------------------------------
    # TSV index builder
    # ------------------------------------------------------------------

    @staticmethod
    def _tsv_reader(fh):
        """csv.DictReader that skips ## comment lines."""
        return csv.DictReader(
            (line for line in fh if not line.startswith("##")),
            delimiter="\t",
        )

    def _build_tsv_index(self):
        """Parse variant_summary.txt.gz → rsid → list[tuple]."""
        fpath = self._tsv_dir / "variant_summary.txt.gz"
        logger.info("Loading ClinVar variant_summary ...")
        start = time.time()
        index: Dict[str, List[tuple]] = {}
        row_count = 0

        with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                row_count += 1
                rs_raw = row.get("RS# (dbSNP)", "")
                if not rs_raw or rs_raw == "-1" or rs_raw == "-":
                    continue
                rs_raw = rs_raw.strip()
                rsid = _intern(f"rs{rs_raw}") if not rs_raw.startswith("rs") else _intern(rs_raw)

                entry = (
                    row.get("AlleleID", "").strip(),             # 0  _E_AID
                    row.get("VariationID", "").strip(),          # 1  _E_VID
                    _intern(row.get("Type", "").strip()),        # 2  _E_TYPE
                    row.get("ClinicalSignificance", "").strip(), # 3  _E_SIG
                    row.get("PhenotypeList", "").strip(),        # 4  _E_COND
                    row.get("PhenotypeIDS", "").strip(),         # 5  _E_PHIDS
                    row.get("RCVaccession", "").strip(),         # 6  _E_RCV
                    _intern(row.get("GeneSymbol", "").strip()),  # 7  _E_GENE
                    row.get("GeneID", "").strip(),               # 8  _E_GID
                    _intern(row.get("Origin", "").strip()),      # 9  _E_ORIGIN
                    _intern(row.get("Assembly", "").strip()),    # 10 _E_ASM
                    row.get("ReviewStatus", "").strip(),         # 11 _E_REV
                    _intern(row.get("Chromosome", "").strip()),  # 12 _E_CHR
                    row.get("Start", "").strip(),                # 13 _E_START
                    row.get("Stop", "").strip(),                 # 14 _E_STOP
                )

                if rsid in index:
                    index[rsid].append(entry)
                else:
                    index[rsid] = [entry]

        self._index = index
        self._files_loaded.append("tsv/variant_summary.txt.gz")
        logger.info(
            "  variant_summary: %d unique rsids from %d rows in %.1fs",
            len(index), row_count, time.time() - start,
        )

    # ------------------------------------------------------------------
    # VCF index builder
    # ------------------------------------------------------------------

    def _build_vcf_index(self):
        """Parse clinvar.vcf.gz → rsid → list[tuple].

        VCF provides data not in TSVs: allele frequencies (AF_ESP, AF_EXAC,
        AF_TGP), molecular consequences (MC), oncogenicity (ONC), somatic
        clinical impact (SCI), and conflicting classification text (CLNSIGCONF).
        """
        fpath = self._vcf_dir / "clinvar.vcf.gz"
        logger.info("Loading ClinVar VCF ...")
        start = time.time()
        vcf_idx: Dict[str, List[tuple]] = {}
        row_count = 0
        rs_count = 0

        with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line[0] == "#":
                    continue
                row_count += 1

                # VCF columns: CHROM POS ID REF ALT QUAL FILTER INFO
                parts = line.split("\t", 8)
                if len(parts) < 8:
                    continue

                info = self._parse_vcf_info(parts[7])

                rs_raw = info.get("RS")
                if not rs_raw:
                    continue
                rs_count += 1

                rs_list = rs_raw.split(",") if "," in rs_raw else (rs_raw,)

                af_exac = self._parse_float(info.get("AF_EXAC"))
                af_tgp = self._parse_float(info.get("AF_TGP"))
                af_esp = self._parse_float(info.get("AF_ESP"))

                mc_raw = info.get("MC", "")
                mc_text = ""
                if mc_raw:
                    labels = []
                    for mcp in mc_raw.split(","):
                        pipe = mcp.find("|")
                        labels.append(mcp[pipe + 1:] if pipe >= 0 else mcp)
                    mc_text = ", ".join(labels)

                entry = (
                    info.get("ALLELEID", ""),        # 0  _V_AID
                    info.get("CLNSIG", ""),           # 1  _V_SIG
                    info.get("CLNDN", ""),            # 2  _V_COND
                    info.get("CLNREVSTAT", ""),       # 3  _V_REV
                    info.get("CLNHGVS", ""),          # 4  _V_HGVS
                    info.get("GENEINFO", ""),          # 5  _V_GENE
                    mc_text,                           # 6  _V_MC
                    af_exac,                           # 7  _V_EXAC
                    af_tgp,                            # 8  _V_TGP
                    af_esp,                            # 9  _V_ESP
                    info.get("ONC", ""),               # 10 _V_ONC
                    info.get("ONCREVSTAT", ""),        # 11 _V_ONCREV
                    info.get("SCI", ""),               # 12 _V_SCI
                    info.get("CLNSIGCONF", ""),        # 13 _V_SIGCONF
                    _intern(info.get("CLNVC", "")),    # 14 _V_VCTYPE
                    info.get("ORIGIN", ""),             # 15 _V_ORIGIN
                    info.get("CLNVI", ""),              # 16 _V_CLNVI
                    info.get("DBVARID", ""),             # 17 _V_DBVAR
                )

                for rs_val in rs_list:
                    rs_val = rs_val.strip()
                    if rs_val:
                        rsid = _intern(f"rs{rs_val}")
                        if rsid in vcf_idx:
                            vcf_idx[rsid].append(entry)
                        else:
                            vcf_idx[rsid] = [entry]

        self._vcf_index = vcf_idx
        self._files_loaded.append("vcf/clinvar.vcf.gz")
        logger.info(
            "  VCF: %d unique rsids from %d RS-tagged rows (%d total) in %.1fs",
            len(vcf_idx), rs_count, row_count, time.time() - start,
        )

    @staticmethod
    def _parse_vcf_info(info_str: str) -> Dict[str, str]:
        """Parse VCF INFO field (semicolon-separated key=value)."""
        info: Dict[str, str] = {}
        for part in info_str.split(";"):
            eq = part.find("=")
            if eq > 0:
                info[part[:eq]] = part[eq + 1:]
            elif part.strip():
                info[part.strip()] = ""
        return info

    @staticmethod
    def _parse_float(val: Optional[str]) -> Optional[float]:
        if not val or val == ".":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Supplementary TSV loaders
    # ------------------------------------------------------------------

    def _load_citations(self):
        fpath = self._tsv_dir / "var_citations.txt"
        if not fpath.exists():
            return
        start = time.time()
        citations: Dict[str, List[str]] = {}
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                aid = (row.get("#AlleleID") or row.get("AlleleID", "")).strip()
                source = (row.get("citation_source") or "").strip()
                cid = (row.get("citation_id") or "").strip()
                if aid and source == "PubMed" and cid:
                    citations.setdefault(aid, []).append(cid)
        self._citations = citations
        self._files_loaded.append("tsv/var_citations.txt")
        logger.info("  var_citations: %d alleles in %.1fs", len(citations), time.time() - start)

    def _load_gene_conditions(self):
        fpath = self._tsv_dir / "gene_condition_source_id.txt"
        if not fpath.exists():
            return
        start = time.time()
        gc: Dict[str, List[tuple]] = {}
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                genes_str = (row.get("AssociatedGenes") or "").strip()
                disease = (row.get("DiseaseName") or "").strip()
                if not genes_str or not disease:
                    continue
                entry = (
                    disease,
                    (row.get("SourceName") or "").strip(),
                    (row.get("SourceID") or "").strip(),
                    (row.get("DiseaseMIM") or "").strip(),
                )
                for gene in genes_str.split(","):
                    gene = gene.strip()
                    if gene:
                        gc.setdefault(gene, []).append(entry)
        self._gene_conditions = gc
        self._files_loaded.append("tsv/gene_condition_source_id.txt")
        logger.info("  gene_conditions: %d genes in %.1fs", len(gc), time.time() - start)

    def _load_cross_references(self):
        fpath = self._tsv_dir / "cross_references.txt"
        if not fpath.exists():
            return
        start = time.time()
        xrefs: Dict[str, List[tuple]] = {}
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                aid = (row.get("#AlleleID") or row.get("AlleleID", "")).strip()
                db = (row.get("Database") or "").strip()
                xid = (row.get("ID") or "").strip()
                if aid and db and xid and db in _XREF_DBS_OF_INTEREST:
                    xrefs.setdefault(aid, []).append((db, xid))
        self._cross_refs = xrefs
        self._files_loaded.append("tsv/cross_references.txt")
        logger.info("  cross_references: %d alleles in %.1fs", len(xrefs), time.time() - start)

    def _load_disease_names(self):
        fpath = self._tsv_dir / "disease_names.txt"
        if not fpath.exists():
            return
        start = time.time()
        diseases: Dict[str, tuple] = {}
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                name = (row.get("#DiseaseName") or row.get("DiseaseName", "")).strip()
                source = (row.get("SourceName") or "").strip()
                concept_id = (row.get("ConceptID") or "").strip()
                source_id = (row.get("SourceID") or "").strip()
                disease_mim = (row.get("DiseaseMIM") or "").strip()
                category = (row.get("Category") or "").strip()
                entry = (name, source, concept_id, source_id, disease_mim, category)
                if concept_id:
                    diseases[concept_id] = entry
                if source_id and source_id != concept_id:
                    diseases.setdefault(source_id, entry)
        self._diseases = diseases
        self._files_loaded.append("tsv/disease_names.txt")
        logger.info("  disease_names: %d entries in %.1fs", len(diseases), time.time() - start)

    def _load_gene_stats(self):
        fpath = self._tsv_dir / "gene_specific_summary.txt"
        if not fpath.exists():
            return
        start = time.time()
        stats: Dict[str, tuple] = {}

        def _int(v: str) -> int:
            v = (v or "").strip()
            return int(v) if v and v != "-" else 0

        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                symbol = (row.get("#Symbol") or row.get("Symbol", "")).strip()
                if not symbol:
                    continue
                stats[symbol] = (
                    (row.get("GeneID") or "").strip(),
                    _int(row.get("Total_submissions", "0")),
                    _int(row.get("Total_alleles", "0")),
                    _int(row.get("Alleles_reported_Pathogenic_Likely_pathogenic", "0")),
                    (row.get("Gene_MIM_number") or "").strip(),
                    _int(row.get("Number_uncertain", "0")),
                    _int(row.get("Number_with_conflicts", "0")),
                )
        self._gene_stats = stats
        self._files_loaded.append("tsv/gene_specific_summary.txt")
        logger.info("  gene_stats: %d genes in %.1fs", len(stats), time.time() - start)

    def _load_hgvs(self):
        fpath = self._tsv_dir / "hgvs4variation.txt.gz"
        if not fpath.exists():
            return
        start = time.time()
        hgvs: Dict[str, tuple] = {}
        with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                aid = (row.get("AlleleID") or "").strip()
                if not aid or aid == "-" or aid in hgvs:
                    continue
                nuc = (row.get("NucleotideExpression") or "").strip()
                prot = (row.get("ProteinExpression") or "").strip()
                if nuc or prot:
                    hgvs[aid] = (
                        nuc,
                        (row.get("NucleotideChange") or "").strip(),
                        prot,
                        (row.get("ProteinChange") or "").strip(),
                        (row.get("Type") or "").strip(),
                        (row.get("Assembly") or "").strip(),
                    )
        self._hgvs = hgvs
        self._files_loaded.append("tsv/hgvs4variation.txt.gz")
        logger.info("  hgvs: %d alleles in %.1fs", len(hgvs), time.time() - start)

    def _load_allele_genes(self):
        fpath = self._tsv_dir / "allele_gene.txt.gz"
        if not fpath.exists():
            return
        start = time.time()
        ag: Dict[str, tuple] = {}
        with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                aid = (row.get("#AlleleID") or row.get("AlleleID", "")).strip()
                if not aid or aid in ag:
                    continue
                ag[aid] = (
                    _intern((row.get("Symbol") or "").strip()),
                    (row.get("Name") or "").strip(),
                    (row.get("GeneID") or "").strip(),
                    (row.get("Category") or "").strip(),
                )
        self._allele_genes = ag
        self._files_loaded.append("tsv/allele_gene.txt.gz")
        logger.info("  allele_genes: %d alleles in %.1fs", len(ag), time.time() - start)

    def _load_submission_counts(self):
        fpath = self._tsv_dir / "submission_summary.txt.gz"
        if not fpath.exists():
            return
        start = time.time()
        counts: Dict[str, int] = {}
        with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                vid = (row.get("#VariationID") or row.get("VariationID", "")).strip()
                if vid:
                    counts[vid] = counts.get(vid, 0) + 1
        self._submission_counts = counts
        self._files_loaded.append("tsv/submission_summary.txt.gz")
        logger.info("  submission_counts: %d variations in %.1fs", len(counts), time.time() - start)

    def _load_conflicting_interpretations(self):
        fpath = self._tsv_dir / "summary_of_conflicting_interpretations.txt"
        if not fpath.exists():
            return
        start = time.time()
        conflicts: Set[str] = set()
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                vid = (row.get("NCBI_Variation_ID") or row.get("#NCBI_Variation_ID", "")).strip()
                if vid:
                    conflicts.add(vid)
        self._conflicting_variations = conflicts
        self._files_loaded.append("tsv/summary_of_conflicting_interpretations.txt")
        logger.info("  conflicts: %d variations in %.1fs", len(conflicts), time.time() - start)

    def _load_variation_alleles(self):
        fpath = self._tsv_dir / "variation_allele.txt.gz"
        if not fpath.exists():
            return
        start = time.time()
        va: Dict[str, List[str]] = {}
        with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            for row in self._tsv_reader(fh):
                vid = (row.get("#VariationID") or row.get("VariationID", "")).strip()
                aid = (row.get("AlleleID") or "").strip()
                if vid and aid:
                    va.setdefault(vid, []).append(aid)
        self._variation_alleles = va
        self._files_loaded.append("tsv/variation_allele.txt.gz")
        logger.info("  variation_alleles: %d variations in %.1fs", len(va), time.time() - start)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_clinvar_local_instance: Optional[ClinVarLocalService] = None


def get_clinvar_local_service() -> ClinVarLocalService:
    """Return the singleton ClinVarLocalService instance."""
    global _clinvar_local_instance
    if _clinvar_local_instance is None:
        _clinvar_local_instance = ClinVarLocalService()
    return _clinvar_local_instance
