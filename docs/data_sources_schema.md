# Data Sources Schema Reference

This document describes every local data file, its format, chromosome notation, and exactly which fields the ETL or lookup service reads. Use this as the authoritative reference before running imports or debugging zero-hit lookup issues.

---

## Quick Reference

| Source | Files | Format | Chr notation | Real-time lookup | ETL → PG table |
|--------|-------|--------|-------------|-----------------|----------------|
| AlphaMissense | `alpha_missense/*.tsv.gz` | bgzip + tabix (.tbi) | **`chr1`** | ✅ direct tabix | ❌ no ETL |
| ClinVar | `clinvar/tsv/variant_summary.txt.gz` + `clinvar/vcf/clinvar.vcf.gz` | TSV.gz + VCF.gz | **bare `1`** | ❌ PG only | ✅ `clinvar_etl.py` |
| gnomAD CADD | `gnomad/gnomad.genomes.r4.0.indel_inclAnno.tsv.gz` | bgzip + tabix (.tbi) | **bare `1`** | ✅ SQLite cache | 🔴 cache always 0 (GRCh38 vs GRCh37 mismatch) |
| gnomAD-tx | `gnomad/all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz` | bgzip + tabix (.tbi) | **bare `1`** | ✅ direct tabix | ❌ no ETL |
| Ensembl VEP | `ensembl/homo_sapiens/variation/vcf_vep/homo_sapiens_incl_consequences-chr*.vcf.gz` | gzip VCF | **`chr1`** | ✅ SQLite cache | ❌ no PG ETL |
| 1000 Genomes | `1000G/1000GENOMES-phase_3.vcf.gz` | gzip VCF + CSI index | **bare `1`** | ❌ PG only | ✅ `thousand_genomes_etl.py` |

---

## 1. AlphaMissense

**Location:** `data_sources/alpha_missense/`

**Files:**

| File | Size | Purpose |
|------|------|---------|
| `AlphaMissense_hg38.tsv.gz` | ~2 GB | Per-variant pathogenicity scores, GRCh38 coordinates |
| `AlphaMissense_hg38.tsv.gz.tbi` | — | Tabix index for hg38 |
| `AlphaMissense_hg19.tsv.gz` | ~2 GB | Same, GRCh37 coordinates |
| `AlphaMissense_hg19.tsv.gz.tbi` | — | Tabix index for hg19 |
| `AlphaMissense_isoforms_hg38.tsv.gz` | ~4 GB | Per-isoform scores (all transcripts) |
| `AlphaMissense_isoforms_hg38.tsv.gz.tbi` | — | Tabix index |
| `AlphaMissense_gene_hg38.tsv.gz` | small | Gene-level mean scores (GRCh38 transcripts) |
| `AlphaMissense_gene_hg19.tsv.gz` | small | Gene-level mean scores (GRCh37 transcripts) |

**⚠️ CHROMOSOME NOTATION: `chr1`, `chr2`, ..., `chrX`, `chrY`**

**Schema (hg38/hg19 variant files, tab-separated):**

| Col | Field | Type | Notes |
|-----|-------|------|-------|
| 0 | `#CHROM` | string | `chr1` format |
| 1 | `POS` | int | 1-based |
| 2 | `REF` | string | Reference allele |
| 3 | `ALT` | string | Alternate allele |
| 4 | `genome` | string | `hg38` or `hg19` |
| 5 | `uniprot_id` | string | UniProt accession |
| 6 | `transcript_id` | string | Ensembl transcript ID |
| 7 | `protein_variant` | string | e.g. `Q1E` |
| 8 | `am_pathogenicity` | float | 0–1 (higher = more pathogenic) |
| 9 | `am_class` | string | `likely_pathogenic`, `likely_benign`, `ambiguous` |

**Schema (isoforms file, 9 columns — no `uniprot_id`):**

Columns 0–4 same, then: `transcript_id`, `protein_variant`, `am_pathogenicity`, `am_class`

**Schema (gene files, tab-separated):**

| Col | Field | Notes |
|-----|-------|-------|
| 0 | `transcript_id` | Ensembl transcript ID |
| 1 | `mean_pathogenicity` | Mean AM score across all missense variants in transcript |

**How it's queried (`backend/utils/alpha_missense.py`):**
```python
tabix.fetch(chrom_str, pos - 1, pos)   # chrom_str = "chr1" (adds prefix if missing)
# Matches rows where fields[2]==ref AND fields[3]==alt
# Also accepts strand-flipped allele pairs
```

**Lookup path:** Always uses `hg19` first, falls back to `hg38`.  
**Key field extracted:** `am_pathogenicity` (col 8), `am_class` (col 9)

**KNOWN BUG:** Consumer DNA files store chromosomes as bare `1`, `2`, etc. The lookup wraps with `chr` prefix correctly (`chrom if chrom.startswith("chr") else f"chr{chrom}"`). However, user data is GRCh37/hg19 coordinates — the hg19 file is queried first, which is correct.

---

## 2. ClinVar

**Location:** `data_sources/clinvar/`

### 2a. variant_summary.txt.gz (TSV — primary source)

**File:** `clinvar/tsv/variant_summary.txt.gz`  
**⚠️ CHROMOSOME NOTATION: bare `1`, `2`, ..., `X`, `Y`, `MT`**

Used by `clinvar_etl.py` to populate the `clinvar_variants` PostgreSQL table.

**Columns extracted (from `TSV_COLUMNS` in etl):**

| Source column | DB field | Notes |
|--------------|----------|-------|
| `RS# (dbSNP)` | `rsid` | Prefixed `rs` added by ETL |
| `#AlleleID` | `allele_id` | ClinVar AlleleID |
| `VariationID` | `variation_id` | ClinVar VariationID |
| `ClinicalSignificance` | `clinical_significance` | Pipe-delimited, e.g. `Pathogenic/Likely pathogenic` |
| `ReviewStatus` | `review_status` | e.g. `criteria provided, multiple submitters` |
| `PhenotypeList` | `conditions` | Pipe-delimited disease names |
| `Origin` | `origin` | e.g. `germline`, `somatic` |
| `Type` | `variation_type` | e.g. `SNV`, `Indel` |
| `GeneSymbol` | `gene` | Gene symbol |
| `GeneID` | `gene_id` | NCBI GeneID |
| `Chromosome` | `chromosome` | Bare number |
| `Start` | `start_pos` | GRCh37/38 start |
| `Stop` | `stop_pos` | GRCh37/38 stop |
| `Assembly` | `assembly` | `GRCh37` or `GRCh38` |
| `RCVaccession` | `rcv_accession` | Pipe-delimited |
| `PhenotypeIDS` | `phenotype_ids` | OMIM/MedGen/Orphanet IDs |

**Full header (all columns, not all extracted):**
```
#AlleleID  Type  Name  GeneID  GeneSymbol  HGNC_ID  ClinicalSignificance  ClinSigSimple
LastEvaluated  RS# (dbSNP)  nsv/esv (dbVar)  RCVaccession  PhenotypeIDS  PhenotypeList
Origin  OriginSimple  Assembly  ChromosomeAccession  Chromosome  Start  Stop
ReferenceAllele  AlternateAllele  Cytogenetic  ReviewStatus  NumberSubmitters  Guidelines
TestedInGTR  OtherIDs  SubmitterCategories  VariationID  PositionVCF
ReferenceAlleleVCF  AlternateAlleleVCF  SomaticClinicalImpact
SomaticClinicalImpactLastEvaluated  ReviewStatusClinicalImpact  Oncogenicity
OncogenicityLastEvaluated  ReviewStatusOncogenicity
SCVsForAggregateGermlineClassification  SCVsForAggregateSomaticClinicalImpact
SCVsForAggregateOncogenicityClassification
```

### 2b. clinvar.vcf.gz (VCF — secondary source)

**File:** `clinvar/vcf/clinvar.vcf.gz`  
**⚠️ CHROMOSOME NOTATION: bare `1`, `2`, ..., `X`, `Y`, `MT`**

Supplements the TSV with additional molecular consequence fields.

**VCF INFO fields extracted (`VCF_COLUMNS` in etl):**

| INFO key | DB field | Notes |
|---------|----------|-------|
| `RS` | `rsid` | rs-prefixed |
| `ALLELEID` | `allele_id` | |
| `CLNSIG` | `clinical_significance` | |
| `CLNREVSTAT` | `review_status` | |
| `CLNDN` | `conditions` | Disease names |
| `CLNORIGIN` | `origin` | |
| `CLNVC` | `variation_type` | |
| `GENEINFO` | `gene` | `GENE:GENEID` format, gene extracted |
| `MC` | `molecular_consequence` | e.g. `SO:0001587|nonsense` |
| `AF_EXAC` | `af_exac` | ExAC allele frequency |
| `AF_TGP` | `af_tgp` | 1000 Genomes frequency |
| `AF_ESP` | `af_esp` | ESP allele frequency |
| `ONCL` | `oncogenicity` | |
| `SCIL` | `somatic_clinical_impact` | |
| `SCIINCL` | `conflicting_classifications` | |
| `CLNHGVS` | `hgvs_nucleotide` | |

### 2c. gene_condition_source_id.txt (TSV — no header prefix)

**File:** `clinvar/tsv/gene_condition_source_id.txt`

Populates `clinvar_gene_conditions` table. Columns:

```
#GeneID  AssociatedGenes  RelatedGenes  ConceptID  DiseaseName  SourceName  SourceID  DiseaseMIM  LastUpdated
```

DB fields extracted: `gene` (AssociatedGenes), `disease_name`, `source_name`, `source_id`, `disease_mim`

### 2d. gene_specific_summary.txt (TSV)

**File:** `clinvar/tsv/gene_specific_summary.txt`

Populates `clinvar_gene_stats` table. Key columns extracted:

```
Symbol  GeneID  Total_submissions  Total_alleles  Pathogenic/likely_pathogenic  Gene_MIM
```

### Other TSV files (NOT used by ETL — reference only)

| File | Contents |
|------|---------|
| `submission_summary.txt.gz` | Per-submitter interpretation details (`VariationID, ClinicalSignificance, Submitter, SCV, ...`) |
| `allele_gene.txt.gz` | AlleleID → GeneID/Symbol mapping |
| `variation_allele.txt.gz` | VariationID → AlleleID mapping |
| `hgvs4variation.txt.gz` | HGVS expressions per VariationID |
| `cross_references.txt` | Cross-refs to external databases |
| `disease_names.txt` | Disease name normalization |
| `var_citations.txt` | PubMed citations per variant |
| `summary_of_conflicting_interpretations.txt` | Conflict details |
| `organization_summary.txt` | Submitter organization metadata |

---

## 3. gnomAD CADD (Indels/SNVs pathogenicity scores)

**Location:** `data_sources/gnomad/`

### 3a. gnomad.genomes.r4.0.indel_inclAnno.tsv.gz

**File:** `gnomad/gnomad.genomes.r4.0.indel_inclAnno.tsv.gz`  
**Format:** bgzip + tabix (.tbi)  
**⚠️ CHROMOSOME NOTATION: bare `1`, `2`, ..., `X`, `Y`**  
**Build:** GRCh38  
**⚠️ IMPORTANT:** Despite the filename saying "indel", this is a CADD-annotated file covering all variant types. The ETL globs `gnomad*.tsv.gz` to find it.

**Full header (153 columns, `#Chrom` prefix on first column):**

Key columns extracted by `gnomad_etl.py`:

| Source column | DB field | Notes |
|--------------|----------|-------|
| `#Chrom` | `chrom` | Bare chr number |
| `Pos` | `pos` | 1-based |
| `Ref` | `ref` | |
| `Alt` | `alt` | |
| — | `variant_id` | `chrom:pos:ref:alt` composite |
| `AnnoType`/`Type` | `variant_type` | SNV, Indel, etc. |
| `RawScore` | `cadd_raw` | CADD raw score |
| `PHRED` | `cadd_phred` | CADD PHRED-scaled score (key field for pathogenicity) |
| `SIFTcat` | `sift_cat` | `tolerated`, `deleterious` |
| `SIFTval` | `sift_val` | SIFT score 0–1 |
| `PolyPhenCat` | `polyphen_cat` | `benign`, `possibly_damaging`, `probably_damaging` |
| `PolyPhenVal` | `polyphen_val` | PolyPhen score 0–1 |
| `priPhyloP` | `phylop_primate` | PhyloP conservation (primate) |
| `mamPhyloP` | `phylop_mammal` | PhyloP conservation (mammal) |
| `verPhyloP` | `phylop_vertebrate` | PhyloP conservation (vertebrate) |
| `SpliceAI-acc-gain` | `splice_ai_acc_gain` | SpliceAI acceptor gain |
| `SpliceAI-acc-loss` | `splice_ai_acc_loss` | SpliceAI acceptor loss |
| `SpliceAI-don-gain` | `splice_ai_don_gain` | SpliceAI donor gain |
| `SpliceAI-don-loss` | `splice_ai_don_loss` | SpliceAI donor loss |
| `GeneName` | `gene` | Gene symbol |
| `Consequence` | `consequence` | VEP consequence |

**How the gnomAD cache works (`gnomad_cache.py`):**

1. On first run: loads all known `(chromosome, position)` from `genetic_markers` table
2. Scans TSV file contig-by-contig (single sequential pass — much faster than 700K tabix.fetch calls)
3. Matches each row's position against known positions; allele-matches with user variants
4. Writes rsid → compressed JSON blob into SQLite at `data_sources/gnomad/.gnomad_cache/gnomad_cache.db`
5. Subsequent runs: opens SQLite directly, `<1s` startup

**🔴 KNOWN BUG — Cache built with 0 variants (root cause confirmed):**  
`gnomad_cache_meta.json` shows `variant_count: 0` from a Mar 16 build. The file IS discovered, chromosome notation IS consistent (both bare `1`), and the column names DO map correctly. The actual root cause is a **genome build mismatch**:

- `genetic_markers` positions are **GRCh37/hg19** (positions from consumer 23andMe/AncestryDNA files)
- `gnomad.genomes.r4.0.indel_inclAnno.tsv.gz` is annotated against **GRCh38** (stated in `##CADD GRCh38-v1.7` header)

The CADD file position coordinates are on a different reference genome. A position like `chr1:69869 (GRCh37)` is at a completely different location in GRCh38, so no positions match.

**Fix options:**
1. **Preferred**: Download the GRCh37 version of the CADD-annotated gnomAD file (CADD v1.6 for GRCh37)
2. **Alternative**: Liftover `genetic_markers` positions from GRCh37→GRCh38 before the cache scan (expensive; positions in DB are not reliable enough for liftover)
3. **Alternative**: Use `rsid`-based lookup instead of position-based matching (ETL approach) — populate `gnomad_variants` PG table via `gnomad_etl.py` using rsids from the VCF ID column rather than position matching

### 3b. all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz (gnomAD-tx)

**File:** `gnomad/all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz`  
**Format:** bgzip + tabix (.tbi extension)  
**⚠️ CHROMOSOME NOTATION: bare `1`, `2`, ..., `X`, `Y`**

This is NOT used by the gnomAD cache/ETL. It's queried directly by `gnomad_tx.py` via tabix for gene symbol + LoF + GTEx tissue expression per variant.

**Schema (5 columns, tab-separated):**

| Col | Field | Type | Notes |
|-----|-------|------|-------|
| 0 | `chrom` | string | Bare `1`, `2`, etc. |
| 1 | `pos` | int | 1-based |
| 2 | `ref` | string | |
| 3 | `alt` | string | |
| 4 | `tx_annotation` | JSON array | One entry per overlapping transcript |

**tx_annotation entry structure:**
```json
{
  "ensg": "ENSG00000186092",
  "symbol": "OR4F5",
  "csq": "start_lost",
  "lof": null,
  "lof_flag": null,
  "mean_proportion": 0.42,
  "Brain_Cortex": 0.38,
  "Liver": 0.12,
  ... (48 GTEx tissue expression proportions)
}
```

**How it's queried (`gnomad_tx.py`):**
```python
chrom_clean = str(chrom).replace("chr", "")   # strips chr prefix if present
tabix.fetch(chrom_clean, pos - 1, pos)         # 0-based half-open interval
# Matches rows where fields[2].upper()==ref AND fields[3].upper()==alt
```

---

## 4. Ensembl VEP VCF Files

**Location:** `data_sources/ensembl/homo_sapiens/variation/vcf_vep/`

### 4a. homo_sapiens_incl_consequences-chrN.vcf.gz (one per chromosome)

**Files:** 25 files, chr1–22, chrX, chrY, chrMT  
**Format:** gzip VCF (NOT tabix — scanned sequentially by cache builder)  
**⚠️ CHROMOSOME NOTATION: `chr1`, `chr2`, ..., `chrX`, `chrMT`**

Parsed by `ensembl_vep_etl.py` → stored in SQLite at `data_sources/ensembl/.vep_cache/vep_cache.db`.  
Cache has **821,402 variants** (built Mar 16).

**VCF record structure:**
```
#CHROM  POS  ID  REF  ALT  QUAL  FILTER  INFO
chr1    925952  rs745905374  G  A  .  .  dbSNP_156;TSA=SNV;E_Freq;VE=...;CSQ=A|missense_variant|MODERATE|SAMD11|...
```

**INFO fields extracted:**

| INFO key | Extracted as | Notes |
|---------|-------------|-------|
| `ID` column (col 2) | `rsid` | Must start with `rs` |
| `TSA` | `variant_type` | Type of Sequence Alteration |
| `VE` | `vep_consequence` | Simple consequence string |
| `CSQ` | `csq_list` | Full VEP CSQ annotation (see below) |

**CSQ format (pipe-delimited, from `##INFO=<ID=CSQ>` header definition):**
```
Allele|Consequence|IMPACT|SYMBOL|Gene|Feature_type|Feature|BIOTYPE|...
```

Key CSQ subfields extracted by `parse_vcf_line()`:
- `Consequence` → consequence term(s)
- `IMPACT` → `HIGH`, `MODERATE`, `LOW`, `MODIFIER`
- `SYMBOL` → gene symbol  
- `Gene` → Ensembl gene ID
- `Feature` → transcript ID
- `BIOTYPE` → transcript biotype
- `HGVSc`, `HGVSp` → HGVS notations (if present)
- `transcript_consequences` → list of all CSQ entries

**SQLite cache structure:**
```sql
CREATE TABLE vep_data (
    rsid TEXT PRIMARY KEY,
    data BLOB NOT NULL    -- zlib-compressed JSON of the parsed VEP result
)
```

**Stored JSON structure per rsid:**
```json
{
  "found": true,
  "source": "ensembl_vep_local",
  "rsid": "rs745905374",
  "variant_type": "SNV",
  "transcript_consequences": [
    {
      "allele": "A",
      "consequence": "missense_variant",
      "impact": "MODERATE",
      "gene_symbol": "SAMD11",
      "gene_id": "ENSG00000187634",
      "transcript_id": "ENST00000341065",
      "biotype": "protein_coding"
    }
  ]
}
```

### 4b. homo_sapiens_clinically_associated.vcf.gz

Same VCF format as above, but contains only clinically-associated variants. Also scanned by VEP cache builder. Same schema.

### 4c. homo_sapiens_phenotype_associated.vcf.gz

Same VCF format — phenotype-associated variants. Same schema.

### Other Ensembl VCF files (present but NOT used)

| File | Contents | Used? |
|------|---------|-------|
| `homo_sapiens_somatic_incl_consequences.vcf.gz` | Somatic variants | ❌ |
| `homo_sapiens_structural_variations.vcf.gz` | SVs | ❌ |

---

## 5. 1000 Genomes Phase 3

**Location:** `data_sources/1000G/`

**Files:**

| File | Size | Notes |
|------|------|-------|
| `1000GENOMES-phase_3.vcf.gz` | 1.5 GB | Full phase 3 variant calls |
| `1000GENOMES-phase_3.vcf.gz.csi` | 1.7 MB | CSI index (NOT .tbi — use with bcftools, not standard tabix) |

**⚠️ CHROMOSOME NOTATION: bare `1`, `2`, ..., `X`, `Y`, `MT`**  
**Build:** GRCh37 (hg19)

**⚠️ PATH BUG FIXED:** The ETL was looking in `data_sources/ensembl/homo_sapiens/variation/vcf_vep/`. Corrected to `data_sources/1000G/` (`thousand_genomes_etl.py` line 38).

**VCF record structure:**
```
1   10001   rs1570391677   T   A,C   .   .   dbSNP_156;TSA=SNV;E_Freq;VE=intergenic_variant;CSQ=A|intergenic_variant||||,C|intergenic_variant||||
```

**INFO fields extracted by `thousand_genomes_etl.py`:**

| INFO key | DB field | Type | Notes |
|---------|----------|------|-------|
| `AFR` | `af_afr` | float | African population AF (Number=A, one per ALT) |
| `AMR` | `af_amr` | float | Admixed American AF |
| `EAS` | `af_eas` | float | East Asian AF |
| `EUR` | `af_eur` | float | European AF |
| `SAS` | `af_sas` | float | South Asian AF |
| `MA` | `minor_allele` | string | Minor allele |
| `MAF` | `maf` | float | Minor allele frequency |
| `MAC` | `mac` | int | Minor allele count |
| `AA` | `ancestral_allele` | string | Ancestral allele |
| `TSA` | `variant_type` | string | e.g. `SNV`, `indel` |
| `ClinVar_*` | `is_clinvar` | bool | Flag — any ClinVar key present |
| `E_1000G` | `is_1000g` | bool | Flag — 1000G evidence |

**PostgreSQL table (`thousand_genomes_variants`) columns:**
```
chrom, pos, ref, alt, rsid, variant_type,
minor_allele, maf, mac, ancestral_allele,
af_afr, af_amr, af_eas, af_eur, af_sas,
is_clinvar, is_1000g, data_source
```

**Important notes:**
- One row per ALT allele (multi-allelic sites are split)
- The file uses a CSI index, not TBI — NOT queryable via `pysam.TabixFile` (which requires .tbi). The ETL reads it as a plain gzip stream, NOT via tabix
- Lookup is PG-only via `thousand_genomes_local.py` → `ThousandGenomesLocalService.lookup_batch()`

---

## 6. Chromosome Notation Mismatch Summary

This is the root cause of most zero-hit lookup issues:

| Source file | Uses | Markers DB uses | Risk |
|-------------|------|-----------------|------|
| AlphaMissense hg38/hg19 | `chr1` | bare `1` | ✅ Code adds `chr` prefix correctly |
| ClinVar VCF | bare `1` | bare `1` | ✅ OK |
| gnomAD CADD TSV | bare `1` | `chr1` in `genetic_markers` | 🔴 **Cache always builds empty** |
| gnomAD-tx BGZ | bare `1` | bare `1` passed | ✅ Code strips `chr` correctly |
| Ensembl VEP VCFs | `chr1` | — (rsid matched, no chr needed) | ✅ OK |
| 1000G VCF | bare `1` | — (rsid matched, no chr needed) | ✅ OK |

**Fix for gnomAD cache (`gnomad_cache.py` `_load_known_positions`):**
```python
# Current (broken):
chrom_clean = str(chrom).replace('chr', '').strip()
# Result: pos_map keys are ('1', pos) but markers store 'chr1'
# if genetic_markers.chromosome = 'chr1', the replace does nothing,
# key becomes ('chr1', pos) but tabix contigs are '1', '2' — MISMATCH

# Actually the issue is the OPPOSITE: the code correctly strips chr from
# the marker's stored chromosome value. But we need to verify what
# genetic_markers.chromosome actually stores:
SELECT DISTINCT chromosome FROM genetic_markers LIMIT 10;
-- If result is 'chr1': chrom_clean correctly becomes '1' 
-- If result is '1': chrom_clean is already '1', also correct
-- Run this query to diagnose
```

**Confirmed:** `genetic_markers.chromosome` = bare `1`, `2`, ... (no `chr` prefix). Chromosome format is NOT the issue.

**Confirmed root cause:** `genetic_markers.position` values are GRCh37 coordinates (from consumer DNA chip files). The CADD TSV file (`gnomad.genomes.r4.0.indel_inclAnno.tsv.gz`) is annotated on GRCh38. Positions never match → cache always empty.

To verify:
```sql
-- Check a known GRCh37 position:
SELECT chromosome, position FROM genetic_markers WHERE rsid = 'rs9283150';
-- Returns: 1, 565508 (GRCh37 coordinate)
-- GRCh38 position for this rsid is different
```

---

## 7. Running ETL Imports

### ClinVar
```bash
docker exec dna_toolkit-backend-1 uv run python -c "
import asyncio
from backend.services.clinvar_etl import ClinVarETL
async def run():
    etl = ClinVarETL()
    stats = await etl.run_full_import()
    print(stats)
asyncio.run(run())
"
```

### gnomAD
```bash
docker exec dna_toolkit-backend-1 uv run python -c "
import asyncio
from backend.services.gnomad_etl import GnomadETL
async def run():
    etl = GnomadETL()
    stats = await etl.run_full_import()
    print(stats)
asyncio.run(run())
"
```

### 1000 Genomes
```bash
docker exec dna_toolkit-backend-1 uv run python -c "
import asyncio
from backend.services.thousand_genomes_etl import ThousandGenomesETL
async def run():
    etl = ThousandGenomesETL()
    stats = await etl.run_full_import()
    print(stats)
asyncio.run(run())
"
```

### Rebuild gnomAD SQLite cache (after ETL or after fixing chromosome format)
```bash
# Delete old cache to force rebuild
rm data_sources/gnomad/.gnomad_cache/gnomad_cache.db \
   data_sources/gnomad/.gnomad_cache/gnomad_cache_meta.json
# Restart backend — cache rebuilds on startup
docker compose restart backend
```

### Rebuild Ensembl VEP SQLite cache
```bash
rm data_sources/ensembl/.vep_cache/vep_cache.db \
   data_sources/ensembl/.vep_cache/vep_cache_meta.json
docker compose restart backend
```

---

## 8. Environment Variable Overrides

| Variable | Default (in container) | Controls |
|----------|----------------------|---------|
| `ALPHA_MISSENSE_DATA_DIR` | `/app/data_sources/alpha_missense` | AlphaMissense lookup |
| `GNOMAD_DATA_DIR` | `/app/data_sources/gnomad` | gnomAD CADD + gnomAD-tx |
| `GNOMAD_CACHE_DIR` | `/app/data_sources/gnomad/.gnomad_cache` | gnomAD SQLite cache location |
| `ENSEMBL_DATA_DIR` | `/app/data_sources/ensembl/homo_sapiens` | Ensembl VEP VCFs |
| `VEP_CACHE_DIR` | `/app/data_sources/ensembl/.vep_cache` | Ensembl VEP SQLite cache location |
| `TKG_DATA_DIR` | `/app/data_sources/1000G` | 1000 Genomes VCF (**fixed from old path**) |
| `CLINVAR_DATA_DIR` | `/app/data_sources/clinvar` | ClinVar TSV + VCF |
