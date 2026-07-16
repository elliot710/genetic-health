# Annotation Source Audit

Correctness audit of all annotation sources feeding variant analysis, documenting storage tier, pathways, scoring weights, and critical failure modes when sources are absent.

## Summary Table

| Source | Tier | Storage | Table/Cache | Feeds | Weight | Absent Behavior |
|--------|------|---------|-------------|-------|--------|-----------------|
| **ClinVar local** | PostgreSQL + SQLite fallback | clinvar_variants (PG) / direct.db (SQLite) | Variant summary, review status, clinical significance, molecular consequence (VCF ~33%), allele frequencies (VCF ~33%) | clinvar_local 0.30 | Scores None; composite unaffected (alternative clinical significance available) |
| **ClinVar API** | Remote API | shared_variant_annotations.clinvar_data (JSON) | Raw API clinical significance | clinvar 0.30 | Not scored (API deprecated, rarely used) |
| **gnomAD** | SQLite cache + PostgreSQL + BigQuery | gnomad_cache.db (SQLite) + gnomad_variants (PG) | CADD PHRED, SIFT, PolyPhen, PhyloP, SpliceAI, AF (from v2 fallback) | cadd 0.15, gnomad_af 0.10, sift 0.05, polyphen 0.05, conservation 0.05, splice_ai 0.05 | CADD/functional scores: None if absent; AF: fallback to VEP then 1000G, rarity term drops if all unavailable |
| **gnomAD-tx** | Tabix-indexed local files | tx_annotated TSV (tabix) | LoF annotation (HC/LC), GTEx tissue expression | gnomad_tx 0.05 | Scores None; expression context lost |
| **Ensembl VEP** | SQLite cache + API fallback | ensembl_vep.db (SQLite) or API | Molecular consequence, impact, colocated variants (gnomAD frequencies) | ensembl_vep 0.05 | Scores None; consequence = None; gnomAD AF unavailable unless gnomAD local has direct AF |
| **1000 Genomes** | SQLite/PostgreSQL + local TSV | thousand_genomes (PG) or TSV cache | Global allele frequency (maf, af_global) | (rarity fallback) | No weight; used as AF fallback (VEP → gnomAD → 1000G) |
| **AlphaMissense** | Local prediction file | alpha_missense.db (SQLite) or file | Pathogenicity score 0–1 | alpha_missense 0.15 | Scores None if absent |
| **ClinGen** | Local TSV + parsed in-memory | Parsed from TSV file | Gene validity classification | clingen 0.04–0.20 (varies by classification) | Scores None if absent |
| **AlphaFold** | BigQuery | shared_variant_annotations.alphafold_data (JSON) | pLDDT global confidence score | alphafold 0.03 | Scores None; structural context lost |
| **SNPedia** | Remote API | shared_variant_annotations.snpedia_data (JSON) | Raw API response | (not extracted as evidence) | Stored but not scored; ignored by analysis |
| **GWAS Catalog** | Local TSV + SQLite cache | gwas_catalog.db (SQLite) | Genome-wide significant associations (p≤5e-8) | gwas_catalog 0.08 | Scores None; trait associations unavailable |
| **CADD** | Embedded in gnomAD CADD TSV | Part of gnomad_cache.db | CADD PHRED score (phred, interpretation) | cadd 0.15 | Scores None; computational deleteriousness unavailable (must use gnomAD source) |
| **dbNSFP** | Not implemented | N/A | N/A | N/A | Not a separate source; VEP provides SIFT/PolyPhen instead |
| **ChEMBL** | BigQuery | shared_variant_annotations.chembl_data (JSON) | Drug mechanisms, indications, warnings | chembl 0.03 | Scores None; druggability lost |
| **FDA Drug** | BigQuery | shared_variant_annotations.fda_drug_data (JSON) | FDA label CYP enzyme interactions | fda_drug 0.03 | Scores None; pharmacogenomic context lost |
| **LitVar** | Remote API | shared_variant_annotations.litvar_data (JSON) | Publication count | litvar 0.03 | Scores None; literature evidence weight lost |
| **PharmGKB/ClinPGx** | Remote API | shared_variant_annotations.pharmgkb_data (JSON) | Pharmacogenomic interactions | (not extracted as evidence) | Stored but not scored; ignored by analysis |

---

## Detailed Failure Modes

### **Tier 1: Critical Path (Rarity Assessment)**

#### Missing gnomAD + missing VEP colocated AF + missing 1000G
- **Code path**: `resolve_population_frequency()` (backend/services/insight_generators/base/frequency.py:64–114)
  - Step 1: Try Ensembl VEP colocated_variants gnomAD frequencies (line 81–91)
  - Step 2: Try gnomAD local AF (line 95–101)
  - Step 3: Try 1000 Genomes global AF (line 104–112)
  - Returns `None` if all fail (line 114)
- **Historical bug** (now fixed): Missing gnomAD used to drop composite's rarity term entirely. Documented at backend/services/insight_generators/base/frequency.py:75 ("distinct from genuine 0.0").
- **Current behavior**: `None` rarity means "unknown frequency" — callers treat conservatively (do NOT synthesize ultra-rare signal).

#### ClinVar local + VCF data missing allele frequencies
- **Code**: backend/services/clinvar_local.py:692–698 (only vcf rows populate af_exac/af_tgp/af_esp)
- **Root cause**: ~33% of clinvar_variants rows are TSV-sourced; VCF rows contain molecular_consequence + allele frequencies. Documented: "clinvar_variants has molecular_consequence + af_exac/af_tgp/af_esp only on vcf-sourced rows (~33%), NULL on tsv rows".
- **Absent behavior**: `vcf_data.allele_frequencies` dict is empty or missing; frequency resolution falls back to gnomAD/1000G. No error logged.

### **Tier 2: Pathogenicity Scoring (Source Order)**

#### Missing CADD (gnomAD CADD score absent)
- **Code**: backend/services/scoring/source_scorers.py:50–65
- **Trigger**: No CADD TSV files in data_sources/gnomad/ OR gnomad_data['cadd'] is None/missing
- **Behavior**: SourceEvidence not created; `evidence_count` lower, composite score drops ~0.05–0.15 (0.15 weight), no impact on final classification if multiple other sources present
- **Recovery**: Relies on SIFT/PolyPhen (gnomAD predictions) or AlphaMissense

#### Missing AlphaMissense
- **Code**: backend/services/scoring/source_scorers.py:139–160
- **Trigger**: AlphaMissense file unavailable OR lookup returns None
- **Behavior**: SourceEvidence not created; 0.15 weight absent; composite score lowers; confidence may drop from "high" to "moderate"
- **Recovery**: Relies on CADD + SIFT/PolyPhen

#### Missing Ensembl VEP consequence
- **Code**: backend/services/scoring/source_scorers.py:162–191
- **Trigger**: Ensembl lookup fails OR data['found'] = False OR no transcript_consequences
- **Behavior**: SourceEvidence not created (weight 0.05); consequence = None (impacts insight generator matching for "HIGH" impact variants)
- **Recovery**: Uses ClinVar molecular consequence if available; falls back to rsid_gene_map
- **Note**: Local VEP VCF files use simplified CSQ format omitting SYMBOL; gene extracted from rsid_gene_map (backend/services/insight_generators/base/frequency.py:35–40)

### **Tier 3: Low-Impact Missing Sources**

#### Missing gnomAD-tx (LoF + expression)
- **Code**: backend/services/scoring/source_scorers.py:446–475
- **Behavior**: SourceEvidence not created; HC LoF signal (0.80 score) unavailable; tissue expression context lost
- **Impact**: Low (0.05 weight); composite score drops ~0.02–0.04
- **Recovery**: Gene constraint (pLI/LOEUF) from gnomAD provides alternative LoF intolerance signal

#### Missing ClinGen
- **Code**: backend/services/scoring/source_scorers.py:213–238
- **Behavior**: SourceEvidence not created; gene-level validity classification unavailable
- **Impact**: Minimal (0.04–0.20 weight, typically 0.05); affects confidence in genes with ClinGen annotation
- **Recovery**: Relies on gene_constraint metrics

#### Missing AlphaFold
- **Code**: backend/services/scoring/source_scorers.py:259–290
- **Behavior**: SourceEvidence not created; pLDDT (structural confidence) unavailable
- **Impact**: Minimal (0.03 weight); affects interpretation of missense variants in structured regions
- **Recovery**: No alternative; consequence-based scoring used

#### Missing GWAS Catalog
- **Code**: backend/services/scoring/source_scorers.py:193–211
- **Behavior**: SourceEvidence not created if `found` = False; GWS associations (p≤5e-8) unavailable
- **Impact**: Low (0.08 weight); population-level trait association evidence lost
- **Recovery**: No alternative for GWAS signal; variant scored on other pathogenicity evidence

### **Tier 4: Unused/Optional Sources**

#### SNPedia (stored, never scored)
- **Code**: Stored at shared_variant_annotations.snpedia_data (backend/db/models/annotations.py:23)
- **Usage**: Not extracted in source_scorers.py; no SourceEvidence created
- **Behavior**: Variant annotation complete; SNPedia data present but ignored by composite scoring
- **Reason**: API response shape varies; annotation extraction not implemented

#### PharmGKB/ClinPGx (stored, never scored)
- **Code**: Stored at shared_variant_annotations.pharmgkb_data (backend/db/models/annotations.py:22, "pharmgkb_data for backward compat")
- **Usage**: Not extracted in source_scorers.py
- **Behavior**: Variant annotation complete; ClinPGx data present but ignored by pathogenicity scoring
- **Note**: Fetched from remote API but repurposed (column named "pharmgkb_data"); scoring focus is genetic pathogenicity, not pharmacogenomics

#### ChEMBL & FDA Drug (BigQuery, optional enrichment)
- **Code**: backend/services/scoring/source_scorers.py:388–444
- **Tier**: BigQuery (Phase 3 enrichment, not Phase 2 local annotation)
- **Behavior**: If BigQuery unavailable or timeout, SourceEvidence not created; weights 0.03 each
- **Impact**: Minimal; druggability/pharmacogenomic context lost, pathogenicity composite unaffected
- **Recovery**: Flagged as failed source; analysis continues with available annotations

#### LitVar (Remote API, optional)
- **Code**: backend/services/scoring/source_scorers.py:292–316
- **Tier**: Remote API (fetched but rarely cached in shared_variant_annotations)
- **Behavior**: If unavailable, SourceEvidence not created; weight 0.03 lost
- **Impact**: Minimal; literature evidence weight lost, variant study status unknown
- **Recovery**: No alternative; variant scored on other sources

#### dbNSFP (not implemented)
- **Code**: Mentioned in backend/services/api_endpoints.py (query templates) but no separate source
- **Behavior**: VEP provides SIFT/PolyPhen (sourced from gnomAD); no dbNSFP column in shared_variant_annotations
- **Impact**: Zero (alternative sources cover SIFT/PolyPhen)
- **Note**: Could be implemented as PostgreSQL ETL if needed; currently out-of-scope

---

## Normalization & Orientation Notes

### Strand/Orientation
- **Code**: backend/services/annotate/map_generation.py STRAND_COMPLEMENT + backend/services/rare_mutations.py
- **Status**: Alleles are normalized before lookup; forward strand orientation standard
- **Failure mode**: If normalization skipped, position mismatches cause "not found" silently (no error logged)

### ClinVar Review Status (Star Rating)
- **Code**: backend/services/clinvar_local.py:684 (TSV), _aggregate_rows() aggregates to "review_statuses" list (line 733–744)
- **Storage**: clinvar_variants.review_status (PostgreSQL), included in aggregated result
- **Failure mode**: If review_status NULL across all rows, output["review_statuses"] = [] (empty); no default assigned

### Marker ID Denormalization
- **Code**: shared_variant_annotations.rsid denormalized for fast lookup (backend/db/models/annotations.py:17)
- **Index**: unique index on rsid (line 17); marker_id foreign key unique (line 16)
- **Failure mode**: Duplicate rsid in analysis (e.g., same variant in two samples) → marker_id mismatch during upsert; ON CONFLICT handles via coalesce logic (backend/services/annotation_coordinator.py:253–259)

---

## Source-Weight Summary

**High confidence (≥0.15)**:
- ClinVar local: 0.30
- ClinVar API: 0.30
- CADD: 0.15
- AlphaMissense: 0.15
- gnomAD AF: 0.10

**Medium (0.05–0.08)**:
- SIFT, PolyPhen, Conservation, SpliceAI, gnomAD-tx, Gene constraint, ClinVar gene stats, GWAS Catalog: 0.05–0.08

**Low (≤0.03)**:
- LitVar, ChEMBL, FDA Drug, AlphaFold: 0.03

**Unweighted**:
- SNPedia, PharmGKB/ClinPGx: not scored

**Total normalized weight**: ~1.0 (built-in weighting strategy in scoring/models.py:15–32)

