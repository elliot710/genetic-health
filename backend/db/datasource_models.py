"""
Pydantic v2 models for every local data source file.

These models define the exact schema for each file format so that:
  1. ETL workers / direct-readers always parse into a typed structure.
  2. Downstream services receive a validated, normalized record — no raw dicts.
  3. Each model has a ``to_annotation()`` method that converts the raw record
     into the service-level annotation dict stored in SharedVariantAnnotation.

File coverage:
  AlphaMissense    — hg19/hg38 TSV.gz (tabix)
  ClinVar TSV      — variant_summary.txt.gz  (streaming)
  ClinVar VCF      — clinvar.vcf.gz          (tabix)
  gnomAD CADD      — gnomad.genomes.*.tsv.gz (tabix / streaming)
  gnomAD-tx        — all.possible.snvs.tx_annotated.GTEx…tsv.bgz (tabix)
  Ensembl VEP      — homo_sapiens_incl_consequences-chrN.vcf.gz   (streaming)
  1000 Genomes     — 1000GENOMES-phase_3.vcf.gz (streaming / VariantFile+CSI)
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _clean_str(v: Optional[str]) -> Optional[str]:
    """Return None for empty / placeholder strings."""
    if v is None:
        return None
    v = v.strip()
    return None if v in (".", "NA", "nan", "", "-", "N/A") else v


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        import math
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# ===========================================================================
# 1. AlphaMissense
# ===========================================================================

class AlphaMissenseRecord(BaseModel):
    """One row from AlphaMissense_hg19.tsv.gz or AlphaMissense_hg38.tsv.gz.

    File format (tab-separated, no header prefix #):
        #CHROM  POS  REF  ALT  genome  uniprot_id  transcript_id
        protein_variant  am_pathogenicity  am_class
    """
    chrom: str
    pos: int
    ref: str
    alt: str
    genome: str                        # "hg38" or "hg19"
    uniprot_id: Optional[str] = None
    transcript_id: str
    protein_variant: str               # e.g. "Q1E"
    am_pathogenicity: float            # 0.0–1.0
    am_class: Optional[str] = None     # "likely_benign" | "ambiguous" | "likely_pathogenic"

    @field_validator("chrom", mode="before")
    @classmethod
    def strip_chr(cls, v: str) -> str:
        return v.strip()

    @field_validator("am_pathogenicity", mode="before")
    @classmethod
    def parse_float(cls, v: Any) -> float:
        return float(v)

    @classmethod
    def from_tsv_fields(cls, fields: List[str]) -> "AlphaMissenseRecord":
        """Parse a tab-split row (already split, 10 columns)."""
        return cls(
            chrom=fields[0].lstrip("#"),
            pos=int(fields[1]),
            ref=fields[2],
            alt=fields[3],
            genome=fields[4],
            uniprot_id=_clean_str(fields[5]) if len(fields) > 5 else None,
            transcript_id=fields[6] if len(fields) > 6 else "",
            protein_variant=fields[7] if len(fields) > 7 else "",
            am_pathogenicity=float(fields[8]) if len(fields) > 8 else 0.0,
            am_class=_clean_str(fields[9]) if len(fields) > 9 else None,
        )

    def to_annotation(self, rsid: Optional[str] = None) -> Dict[str, Any]:
        """Convert to the alpha_missense_data annotation dict."""
        return {
            "found": True,
            "source": "alpha_missense",
            "rsid": rsid,
            "chrom": self.chrom.replace("chr", ""),
            "pos": self.pos,
            "ref": self.ref,
            "alt": self.alt,
            "genome": self.genome,
            "uniprot_id": self.uniprot_id,
            "transcript_id": self.transcript_id,
            "protein_variant": self.protein_variant,
            "am_pathogenicity": self.am_pathogenicity,
            "am_class": self.am_class,
            # Alias for scoring engine
            "score": self.am_pathogenicity,
            "classification": self.am_class,
        }


# ===========================================================================
# 2. ClinVar
# ===========================================================================

class ClinVarSummaryRecord(BaseModel):
    """One row from variant_summary.txt.gz (tab-separated, has header).

    Key columns (0-indexed after stripping the # header marker):
        AlleleID  Type  Name  GeneID  GeneSymbol  ...  ClinicalSignificance  ...
        RS# (dbSNP)  ...  Assembly  Chromosome  Start  Stop
    """
    rsid: Optional[str] = None          # prefixed with "rs"
    allele_id: Optional[int] = None
    variation_id: Optional[int] = None
    clinical_significance: Optional[str] = None
    review_status: Optional[str] = None
    conditions: Optional[str] = None    # pipe-delimited
    origin: Optional[str] = None
    variation_type: Optional[str] = None
    gene: Optional[str] = None          # GeneSymbol
    gene_id: Optional[str] = None
    chromosome: Optional[str] = None    # bare "1"–"22", "X", "Y", "MT"
    start_pos: Optional[int] = None
    stop_pos: Optional[int] = None
    assembly: Optional[str] = None      # "GRCh37" or "GRCh38"
    rcv_accession: Optional[str] = None
    phenotype_ids: Optional[str] = None

    @classmethod
    def from_row(cls, row: Dict[str, str]) -> "ClinVarSummaryRecord":
        """Parse from a csv.DictReader row (header names as keys)."""
        raw_rs = row.get("RS# (dbSNP)", "") or row.get("DBSNP", "")
        rsid: Optional[str] = None
        if raw_rs and raw_rs.strip() not in (".", "", "-1", "-"):
            try:
                n = int(raw_rs)
                if n > 0:
                    rsid = f"rs{n}"
            except ValueError:
                if raw_rs.startswith("rs"):
                    rsid = raw_rs

        return cls(
            rsid=rsid,
            allele_id=_safe_int(row.get("#AlleleID") or row.get("AlleleID")),
            variation_id=_safe_int(row.get("VariationID")),
            clinical_significance=_clean_str(row.get("ClinicalSignificance")),
            review_status=_clean_str(row.get("ReviewStatus")),
            conditions=_clean_str(row.get("PhenotypeList")),
            origin=_clean_str(row.get("Origin")),
            variation_type=_clean_str(row.get("Type")),
            gene=_clean_str(row.get("GeneSymbol")),
            gene_id=_clean_str(row.get("GeneID")),
            chromosome=_clean_str(row.get("Chromosome")),
            start_pos=_safe_int(row.get("Start")),
            stop_pos=_safe_int(row.get("Stop")),
            assembly=_clean_str(row.get("Assembly")),
            rcv_accession=_clean_str(row.get("RCVaccession")),
            phenotype_ids=_clean_str(row.get("PhenotypeIDS")),
        )

    def to_annotation(self) -> Dict[str, Any]:
        """Convert to the clinvar_local_data fragment format."""
        conditions_list = (
            [c.strip() for c in self.conditions.split("|") if c.strip()]
            if self.conditions else []
        )
        return {
            "found": True,
            "source": "clinvar_local",
            "rsid": self.rsid,
            "clinical_significances": [self.clinical_significance] if self.clinical_significance else [],
            "conditions": conditions_list,
            "genes": [self.gene] if self.gene else [],
            "review_statuses": [self.review_status] if self.review_status else [],
            "allele_ids": [self.allele_id] if self.allele_id else [],
            "ids": [self.variation_id] if self.variation_id else [],
            "assembly": self.assembly,
            "chromosome": self.chromosome,
            "start": str(self.start_pos) if self.start_pos else None,
            "stop": str(self.stop_pos) if self.stop_pos else None,
        }


class ClinVarVcfRecord(BaseModel):
    """One record from clinvar.vcf.gz (parsed from VCF INFO fields).

    Chrom uses bare notation: 1, 2, …, X, Y, MT
    """
    chrom: str
    pos: int
    ref: str
    alt: str
    rsid: Optional[str] = None
    allele_id: Optional[int] = None
    clinical_significance: Optional[str] = None  # from CLNSIG
    review_status: Optional[str] = None           # from CLNREVSTAT
    conditions: Optional[str] = None              # from CLNDN (pipe-separated)
    origin: Optional[str] = None                  # from CLNORIGIN
    variation_type: Optional[str] = None          # from CLNVC
    gene: Optional[str] = None                    # from GENEINFO
    molecular_consequence: Optional[str] = None   # from MC
    af_exac: Optional[float] = None
    af_tgp: Optional[float] = None
    af_esp: Optional[float] = None
    oncogenicity: Optional[str] = None
    somatic_clinical_impact: Optional[str] = None
    hgvs_nucleotide: Optional[str] = None

    @classmethod
    def from_vcf_fields(
        cls, chrom: str, pos: int, id_field: str, ref: str, alt: str, info_str: str
    ) -> "ClinVarVcfRecord":
        """Parse a raw VCF line's components into the model."""
        info = _parse_vcf_info(info_str)

        rsid: Optional[str] = None
        if id_field and id_field != ".":
            raw = info.get("RS", "")
            if raw and raw not in (".", ""):
                rsid = f"rs{raw}" if not raw.startswith("rs") else raw
            elif id_field.startswith("rs"):
                rsid = id_field

        # GENEINFO format: "GENE:GENEID"
        gene_raw = info.get("GENEINFO", "")
        gene = gene_raw.split(":")[0] if gene_raw and ":" in gene_raw else _clean_str(gene_raw)

        return cls(
            chrom=chrom.replace("chr", ""),
            pos=pos,
            ref=ref,
            alt=alt,
            rsid=rsid,
            allele_id=_safe_int(info.get("ALLELEID")),
            clinical_significance=_clean_str(info.get("CLNSIG")),
            review_status=_clean_str(info.get("CLNREVSTAT")),
            conditions=_clean_str(info.get("CLNDN")),
            origin=_clean_str(info.get("CLNORIGIN")),
            variation_type=_clean_str(info.get("CLNVC")),
            gene=_clean_str(gene),
            molecular_consequence=_clean_str(info.get("MC")),
            af_exac=_safe_float(info.get("AF_EXAC")),
            af_tgp=_safe_float(info.get("AF_TGP")),
            af_esp=_safe_float(info.get("AF_ESP")),
            oncogenicity=_clean_str(info.get("ONCL")),
            somatic_clinical_impact=_clean_str(info.get("SCIL")),
            hgvs_nucleotide=_clean_str(info.get("CLNHGVS")),
        )

    def to_annotation(self) -> Dict[str, Any]:
        conditions_list = (
            [c.strip() for c in self.conditions.split("|") if c.strip()]
            if self.conditions else []
        )
        result: Dict[str, Any] = {
            "found": True,
            "source": "clinvar_local",
            "rsid": self.rsid,
            "chrom": self.chrom,
            "pos": self.pos,
            "ref": self.ref,
            "alt": self.alt,
            "clinical_significances": [self.clinical_significance] if self.clinical_significance else [],
            "conditions": conditions_list,
            "genes": [self.gene] if self.gene else [],
            "review_statuses": [self.review_status] if self.review_status else [],
        }
        if self.molecular_consequence:
            result["molecular_consequences"] = [self.molecular_consequence]
        allele_freqs: Dict[str, float] = {}
        if self.af_exac is not None:
            allele_freqs["exac"] = self.af_exac
        if self.af_tgp is not None:
            allele_freqs["tgp"] = self.af_tgp
        if self.af_esp is not None:
            allele_freqs["esp"] = self.af_esp
        if allele_freqs:
            result["allele_frequencies"] = allele_freqs
        return result


# ===========================================================================
# 3. gnomAD CADD TSV
# ===========================================================================

class GnomadCaddRecord(BaseModel):
    """One deduplicated row from gnomad.genomes.*.tsv.gz (CADD-annotated).

    Chromosome notation: bare "1"–"22", "X", "Y"
    Genome build: GRCh38 (v4) — note mismatch with user data (GRCh37)!
    """
    chrom: str
    pos: int
    ref: str
    alt: str
    variant_type: Optional[str] = None  # "SNV", "INS", "DEL"
    gene: Optional[str] = None
    consequence: Optional[str] = None
    cadd_raw: Optional[float] = None
    cadd_phred: Optional[float] = None
    sift_cat: Optional[str] = None
    sift_val: Optional[float] = None
    polyphen_cat: Optional[str] = None
    polyphen_val: Optional[float] = None
    phylop_primate: Optional[float] = None
    phylop_mammal: Optional[float] = None
    phylop_vertebrate: Optional[float] = None
    splice_ai_acc_gain: Optional[float] = None
    splice_ai_acc_loss: Optional[float] = None
    splice_ai_don_gain: Optional[float] = None
    splice_ai_don_loss: Optional[float] = None

    @classmethod
    def from_parsed(cls, parsed: Dict[str, Any]) -> "GnomadCaddRecord":
        """Construct from the dict returned by gnomad_cache._parse_cadd_row()."""
        return cls(
            chrom=str(parsed["chrom"]).replace("chr", ""),
            pos=int(parsed["pos"]),
            ref=parsed["ref"],
            alt=parsed["alt"],
            variant_type=_clean_str(parsed.get("variant_type")),
            gene=_clean_str(parsed.get("gene")),
            consequence=_clean_str(parsed.get("consequence")),
            cadd_raw=parsed.get("cadd_raw"),
            cadd_phred=parsed.get("cadd_phred"),
            sift_cat=_clean_str(parsed.get("sift_cat")),
            sift_val=parsed.get("sift_val"),
            polyphen_cat=_clean_str(parsed.get("polyphen_cat")),
            polyphen_val=parsed.get("polyphen_val"),
            phylop_primate=parsed.get("phylop_primate"),
            phylop_mammal=parsed.get("phylop_mammal"),
            phylop_vertebrate=parsed.get("phylop_vertebrate"),
            splice_ai_acc_gain=parsed.get("splice_ai_acc_gain"),
            splice_ai_acc_loss=parsed.get("splice_ai_acc_loss"),
            splice_ai_don_gain=parsed.get("splice_ai_don_gain"),
            splice_ai_don_loss=parsed.get("splice_ai_don_loss"),
        )

    @property
    def max_splice_ai(self) -> Optional[float]:
        scores = [s for s in [
            self.splice_ai_acc_gain, self.splice_ai_acc_loss,
            self.splice_ai_don_gain, self.splice_ai_don_loss,
        ] if s is not None]
        return max(scores) if scores else None

    def to_annotation(self, rsid: Optional[str] = None) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "found": True,
            "source": "gnomad_local",
            "rsid": rsid,
            "chrom": self.chrom,
            "pos": self.pos,
            "ref": self.ref,
            "alt": self.alt,
            "variant_id": f"{self.chrom}-{self.pos}-{self.ref}-{self.alt}",
            "variant_type": self.variant_type,
            "gene": self.gene,
            "consequence": self.consequence,
        }
        if self.cadd_phred is not None or self.cadd_raw is not None:
            result["cadd"] = {
                "raw": self.cadd_raw,
                "phred": self.cadd_phred,
                "interpretation": _interpret_cadd(self.cadd_phred),
            }
        predictions: Dict[str, Any] = {}
        if self.sift_cat is not None:
            predictions["sift"] = {"category": self.sift_cat, "score": self.sift_val}
        if self.polyphen_cat is not None:
            predictions["polyphen"] = {"category": self.polyphen_cat, "score": self.polyphen_val}
        if predictions:
            result["predictions"] = predictions
        conservation: Dict[str, float] = {}
        for key, val in [
            ("primate", self.phylop_primate),
            ("mammal", self.phylop_mammal),
            ("vertebrate", self.phylop_vertebrate),
        ]:
            if val is not None:
                conservation[key] = val
        if conservation:
            result["conservation"] = conservation
        max_splice = self.max_splice_ai
        if max_splice is not None:
            result["splice_ai"] = {
                "acceptor_gain": self.splice_ai_acc_gain,
                "acceptor_loss": self.splice_ai_acc_loss,
                "donor_gain": self.splice_ai_don_gain,
                "donor_loss": self.splice_ai_don_loss,
                "max_score": max_splice,
            }
        return result


# ===========================================================================
# 4. gnomAD-tx transcript annotation
# ===========================================================================

class GnomadTxEntry(BaseModel):
    """One entry in the tx_annotation JSON array from the gnomAD-tx bgz file.

    Each variant row may have multiple transcripts.
    """
    ensg: Optional[str] = None
    symbol: Optional[str] = None       # gene symbol
    csq: Optional[str] = None          # VEP consequence
    lof: Optional[str] = None          # "HC", "LC", or None
    lof_flag: Optional[str] = None
    mean_proportion: Optional[float] = None
    top_tissues: Optional[Dict[str, float]] = None  # top-10 tissues by expression

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GnomadTxEntry":
        # Collect non-standard keys as tissue expression
        _STD = {"ensg", "symbol", "csq", "lof", "lof_flag", "mean_proportion"}
        tissues: Dict[str, float] = {}
        for k, v in d.items():
            if k not in _STD and v not in (None, "NaN", "nan", ""):
                try:
                    tissues[k] = float(v)
                except (ValueError, TypeError):
                    pass
        top = dict(sorted(tissues.items(), key=lambda x: x[1], reverse=True)[:10]) if tissues else None

        mean_raw = d.get("mean_proportion")
        mean: Optional[float] = None
        if mean_raw not in (None, "NaN", "nan", ""):
            try:
                mean = float(mean_raw)
            except (ValueError, TypeError):
                pass

        return cls(
            ensg=_clean_str(d.get("ensg")),
            symbol=_clean_str(d.get("symbol")),
            csq=_clean_str(d.get("csq")),
            lof=_clean_str(d.get("lof")),
            lof_flag=_clean_str(d.get("lof_flag")),
            mean_proportion=mean,
            top_tissues=top,
        )


class GnomadTxRecord(BaseModel):
    """One row from all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz.

    Chromosome notation: bare "1"–"22", "X", "Y"
    Build: GRCh37 (gnomAD v2.1.1)
    """
    chrom: str
    pos: int
    ref: str
    alt: str
    transcripts: List[GnomadTxEntry] = Field(default_factory=list)

    @classmethod
    def from_tabix_row(cls, row_str: str) -> Optional["GnomadTxRecord"]:
        """Parse a raw tabix row string."""
        import json
        fields = row_str.split("\t")
        if len(fields) < 5:
            return None
        try:
            annotations = json.loads(fields[4])
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(annotations, list):
            return None
        return cls(
            chrom=fields[0].replace("chr", ""),
            pos=int(fields[1]),
            ref=fields[2].upper(),
            alt=fields[3].upper(),
            transcripts=[GnomadTxEntry.from_dict(a) for a in annotations],
        )

    def to_annotation(self, rsid: Optional[str] = None) -> Dict[str, Any]:
        """Convert to gnomad_tx_data annotation dict."""
        if not self.transcripts:
            return {"found": False, "source": "gnomad_tx"}

        primary = max(
            self.transcripts,
            key=lambda t: t.mean_proportion if t.mean_proportion is not None else -1.0,
        )
        transcript_dicts = [
            {
                "ensg": t.ensg,
                "symbol": t.symbol,
                "csq": t.csq,
                "lof": t.lof,
                "lof_flag": t.lof_flag,
                "mean_expression": t.mean_proportion,
                "top_tissues": t.top_tissues,
            }
            for t in self.transcripts
        ]
        result: Dict[str, Any] = {
            "found": True,
            "source": "gnomad_tx",
            "rsid": rsid,
            "chrom": self.chrom,
            "pos": self.pos,
            "ref": self.ref,
            "alt": self.alt,
            "gene": primary.symbol,
            "consequence": primary.csq,
            "lof": primary.lof,
            "transcript_count": len(self.transcripts),
            "transcripts": transcript_dicts,
        }
        if primary.mean_proportion is not None:
            result["mean_expression"] = round(primary.mean_proportion, 6)
        return result


# ===========================================================================
# 5. Ensembl VEP VCF
# ===========================================================================

class EnsemblVepConsequence(BaseModel):
    """One CSQ entry (pipe-split) from Ensembl VEP VCF INFO=CSQ."""
    allele: Optional[str] = None
    consequence: Optional[str] = None    # missense_variant, etc.
    impact: Optional[str] = None         # HIGH/MODERATE/LOW/MODIFIER
    gene_symbol: Optional[str] = None
    gene_id: Optional[str] = None
    transcript_id: Optional[str] = None
    biotype: Optional[str] = None
    hgvsc: Optional[str] = None
    hgvsp: Optional[str] = None

    @classmethod
    def from_fields(cls, fields: List[str], col_names: List[str]) -> "EnsemblVepConsequence":
        idx = {n: i for i, n in enumerate(col_names)}
        def _g(name: str) -> Optional[str]:
            i = idx.get(name)
            return _clean_str(fields[i]) if i is not None and i < len(fields) else None

        return cls(
            allele=_g("Allele"),
            consequence=_g("Consequence"),
            impact=_g("IMPACT"),
            gene_symbol=_g("SYMBOL"),
            gene_id=_g("Gene"),
            transcript_id=_g("Feature"),
            biotype=_g("BIOTYPE"),
            hgvsc=_g("HGVSc"),
            hgvsp=_g("HGVSp"),
        )


class EnsemblVepRecord(BaseModel):
    """One VCF record from homo_sapiens_incl_consequences-chrN.vcf.gz.

    Chromosome notation: chr1, chr2, …, chrX, chrMT
    """
    rsid: str                             # must start with "rs"
    chrom: str
    pos: int
    ref: str
    alt: str
    variant_type: Optional[str] = None   # from TSA field
    most_severe_consequence: Optional[str] = None
    transcript_consequences: List[EnsemblVepConsequence] = Field(default_factory=list)

    def to_annotation(self) -> Dict[str, Any]:
        """Convert to ensembl_data annotation dict (Ensembl API-compatible shape)."""
        tc_list = [
            {
                "allele": tc.allele,
                "consequence_terms": [tc.consequence] if tc.consequence else [],
                "impact": tc.impact,
                "gene_symbol": tc.gene_symbol,
                "gene_id": tc.gene_id,
                "transcript_id": tc.transcript_id,
                "biotype": tc.biotype,
                "hgvsc": tc.hgvsc,
                "hgvsp": tc.hgvsp,
            }
            for tc in self.transcript_consequences
        ]
        entry = {
            "seq_region_name": self.chrom.replace("chr", ""),
            "start": self.pos,
            "allele_string": f"{self.ref}/{self.alt}",
            "most_severe_consequence": self.most_severe_consequence,
            "transcript_consequences": tc_list,
        }
        return {
            "found": True,
            "source": "ensembl_vep_local",
            "rsid": self.rsid,
            "variant_type": self.variant_type,
            "data": [entry],
        }


# ===========================================================================
# 6. 1000 Genomes VCF
# ===========================================================================

class ThousandGenomesRecord(BaseModel):
    """One split-allele record from 1000GENOMES-phase_3.vcf.gz.

    Chromosome notation: bare "1"–"22", "X", "Y", "MT"
    Build: GRCh37
    """
    chrom: str
    pos: int
    ref: str
    alt: str
    rsid: Optional[str] = None
    variant_type: Optional[str] = None  # TSA field
    minor_allele: Optional[str] = None
    maf: Optional[float] = None
    mac: Optional[int] = None
    ancestral_allele: Optional[str] = None
    af_afr: Optional[float] = None
    af_amr: Optional[float] = None
    af_eas: Optional[float] = None
    af_eur: Optional[float] = None
    af_sas: Optional[float] = None

    @property
    def global_af(self) -> Optional[float]:
        """Approximate global AF as simple mean of available populations."""
        vals = [v for v in [self.af_afr, self.af_amr, self.af_eas, self.af_eur, self.af_sas] if v is not None]
        return sum(vals) / len(vals) if vals else self.maf

    _POP_NAMES: ClassVar[Dict[str, str]] = {
        "afr": "African",
        "amr": "Admixed American",
        "eas": "East Asian",
        "eur": "European",
        "sas": "South Asian",
    }

    def to_annotation(self) -> Dict[str, Any]:
        """Convert to thousand_genomes_data annotation dict."""
        pop_freqs: Dict[str, Any] = {}
        for code, name in self._POP_NAMES.items():
            val = getattr(self, f"af_{code}", None)
            if val is not None:
                pop_freqs[code] = {"name": name, "af": val}

        return {
            "found": True,
            "source": "1000genomes_local",
            "rsid": self.rsid,
            "chrom": self.chrom,
            "pos": self.pos,
            "ref": self.ref,
            "alt": self.alt,
            "variant_type": self.variant_type,
            "minor_allele": self.minor_allele,
            "maf": self.maf,
            "mac": self.mac,
            "ancestral_allele": self.ancestral_allele,
            "population_frequencies": pop_freqs,
            "global_af": self.global_af,
        }


# ===========================================================================
# Shared helpers (private)
# ===========================================================================

def _parse_vcf_info(info_str: str) -> Dict[str, str]:
    """Parse a VCF INFO field string into a key→value dict."""
    result: Dict[str, str] = {}
    for token in info_str.split(";"):
        if "=" in token:
            k, _, v = token.partition("=")
            result[k.strip()] = v.strip()
        elif token.strip():
            result[token.strip()] = "1"
    return result


def _interpret_cadd(phred: Optional[float]) -> Optional[str]:
    if phred is None:
        return None
    if phred >= 30:
        return "Very high pathogenicity (top 0.1%)"
    if phred >= 20:
        return "High pathogenicity (top 1%)"
    if phred >= 15:
        return "Moderate pathogenicity (top ~3%)"
    if phred >= 10:
        return "Low pathogenicity (top ~10%)"
    return "Likely benign"
