# Architecture Documentation

> Last updated: 2026-03-18 — based on full codebase audit of all backend services, DB schema, insights pipeline, annotation sources, and frontend integration.

---

## 1. System Overview

The Genetic Health Analysis Toolkit is a full-stack platform that:
1. Accepts raw genetic data (VCF or consumer CSV)
2. Parses and deduplicates genetic markers into a global catalog
3. Annotates variants against 6+ local/remote data sources
4. Scores variant pathogenicity using a weighted composite engine
5. Generates 14 categories of health/trait insights via a map-driven generator system
6. Presents results on a dashboard with per-category panels

### Services

| Service | Technology | Container |
|---------|-----------|-----------|
| Frontend | Next.js 15, React, Tailwind CSS 4, shadcn/ui | `dna_toolkit-frontend-1` |
| Backend API | FastAPI, SQLAlchemy 2.0 (async), Python 3.13 | `dna_toolkit-backend-1` |
| Background Worker | Same image, `worker.py` entry point | `dna_toolkit-worker-1` |
| Database | PostgreSQL 16 | `dna_toolkit-postgres-1` |

---

## 2. Data Flow Pipeline

```
User uploads CSV/VCF
        │
        ▼
┌─────────────────────┐
│  variant_uploader.py │  Parse file → create GeneticMarker rows (dedup by rsid)
│                      │  Create AnalysisVariant rows (user genotype per marker)
└────────┬────────────┘
         │
         ▼
┌─────────────────────────────┐
│  analysis_queue.py / worker │  Picks up PENDING analyses, dispatches to
│                              │  ComprehensiveAnalysisService.process_analysis()
└────────┬────────────────────┘
         │
         ▼
╔═════════════════════════════════════════════════════════════════╗
║  ComprehensiveAnalysisService  (analysis_service.py)           ║
║                                                                 ║
║  Phase 1: Build rsid→gene map  (ClinVar PG + Ensembl local)    ║
║           ↓                                                     ║
║  Phase 2: Annotate variants                                     ║
║           • Check SharedVariantAnnotation cache (reuse)         ║
║           • Bulk local annotation (6 sources)                   ║
║           • Backfill missing sources for cached annotations     ║
║           • Score pathogenicity (scoring_engine.py)              ║
║           ↓                                                     ║
║  Phase 3: BigQuery enrichment (optional, currently disabled)    ║
║           ↓                                                     ║
║  Phase 4: Generate insights (14 generators)                     ║
║           • Build VariantProfile for every variant (ONCE)       ║
║           • Run each generator with shared GeneratorContext     ║
║           • Store results in per-category DB tables              ║
╚═════════════════════════════════════════════════════════════════╝
```

---

## 3. Database Architecture

### 3.1 Core Tables

| Table | Purpose | Lifecycle |
|-------|---------|-----------|
| `users` | Accounts | Persistent |
| `genetic_analyses` | Analysis header (status, progress, logs) | Soft-deletable |
| `genetic_markers` | Global variant catalog (rsid, chr, pos, ref, alt) | **Never deleted** |
| `analysis_variants` | User → marker link + genotype | CASCADE delete with analysis |
| `shared_variant_annotations` | Per-marker annotation cache (1 row per rsid) | **Never deleted** |
| `variant_annotations` | User-specific refs to shared annotations | CASCADE delete |

### 3.2 Annotation Columns on `shared_variant_annotations`

| Column | Source | Type |
|--------|--------|------|
| `ensembl_data` | Ensembl VEP (local VCF + remote API) | JSON |
| `clinvar_data` | ClinVar API (remote) | JSON |
| `clinvar_local_data` | ClinVar PostgreSQL tables | JSON |
| `gnomad_data` | gnomAD (local TSV + SQLite cache + BigQuery) | JSON |
| `gnomad_tx_data` | gnomAD transcript annotation (tabix) | JSON |
| `thousand_genomes_data` | 1000 Genomes Phase 3 (PostgreSQL) | JSON |
| `alpha_missense_data` | AlphaMissense (tabix) | JSON |
| `pharmgkb_data` | ClinPGx API (misnamed column) | JSON |
| `snpedia_data` | SNPedia API | JSON |
| `litvar_data` | LitVar/PubMed API | JSON |
| `chembl_data` | ChEMBL (BigQuery) | JSON |
| `fda_drug_data` | FDA drug labels (BigQuery) | JSON |
| `alphafold_data` | AlphaFold (BigQuery) | JSON |

### 3.3 Insight Tables (all CASCADE delete with analysis)

`health_risks`, `drug_responses`, `physical_traits`, `nutrition_traits`, `sports_performance`, `cognitive_profiles`, `personality_traits`, `ancestry_results`, `carrier_status`, `wellness_metrics`, `methylation_profiles`, `detoxification_profiles`, `rare_mutations`, `uncommon_mutations`

### 3.4 Configuration Tables

| Table | Purpose |
|-------|---------|
| `variant_mappings` | rsid/gene → category mappings (manual + auto-discovered) |
| `panel_marker_configs` | Panel↔marker associations (admin UI) |
| `category_rules` | Auto-categorization rules engine |
| `annotation_source_configs` | Enable/disable annotation sources |
| `pending_discoveries` | Auto-discovered markers awaiting admin approval |

### 3.5 Data Source Tables (ETL-populated)

| Table | Row Count | Source File |
|-------|-----------|-------------|
| `clinvar_variants` | ~8.7M | `data_sources/clinvar/` TSV + VCF |
| `clinvar_gene_conditions` | — | `gene_condition_source_id.txt` |
| `clinvar_gene_stats` | — | `gene_specific_summary.txt` |
| `gnomad_variants` | ~0 (ETL not run) | `data_sources/gnomad/*.tsv.gz` |
| `gnomad_gene_constraints` | — | BigQuery |
| `ancestry_aims_panel` | ~60K (FST≥0.70) | Migration 010 (from 1000G) |

---

## 4. Variant Mapping System (Registry)

### 4.1 How Mappings Work

The `variant_mappings` table is the **central knowledge base** that maps genetic variants to health insights. Each row contains:

```
category: 'health' | 'drug' | 'carrier' | 'physical' | ...
map_type: 'rsid' | 'gene'
key:      'rs7903146' (for rsid) or 'CYP2D6' (for gene)
data:     JSON with category-specific fields
```

At analysis time, `_load_registry()` loads all active mappings into an in-memory dict:
```python
registry[category][map_type][key] = data
# e.g. registry['health']['rsid']['rs7903146'] = {"condition": "Type 2 Diabetes", "risk_multiplier": 1.4}
```

### 4.2 Two Sources of Mappings

1. **Manual (curated)**: ~100 hand-picked mappings with evidence-based risk multipliers
2. **Auto-discovered (~20,000)**: Generated by `auto_categorizer.py` running `category_rules` against ClinVar data

### 4.3 Auto-Categorization Rules Engine

`category_rules` table defines rules like:
- `clinvar_significance = 'Pathogenic'` → category `health`, risk_multiplier=3.0
- `gene_list = 'CYP2D6,CYP2C19,...'` → category `drug`
- `clinvar_condition_keyword = 'cancer'` → category `health`

The auto-categorizer (`auto_categorizer.py`) queries ClinVar, creates `variant_mappings` rows with `is_auto_discovered=true`, capped at 2,000 per category.

### 4.4 Data Shape by Category

**Health rsid map:**
```json
{"condition": "Type 2 Diabetes", "risk_multiplier": 1.4}
```

**Drug rsid map:**
```json
{"gene": "CYP2C9", "drugs": ["warfarin", "phenytoin"]}
```

**Drug gene map:**
```json
{"gene": "CYP2D6", "drugs": [["drug_name", "response_type", "recommendation"]]}
```

**Carrier rsid map:**
```json
{"condition": "Sickle Cell Disease", "status": "non-carrier"}
```

**Trait-based categories (physical, nutrition, sports, cognitive, personality, wellness, methylation, detox):**
```json
{"trait": "...", "category": "...", "metric": "...", ...category-specific-fields}
```

---

## 5. Insight Generation Pipeline

### 5.1 Generator Architecture

All 14 generators follow the same contract:
```python
async def generate_X(ctx: GeneratorContext) -> int:
    # Returns count of insight rows created
```

`GeneratorContext` carries:
- `variants`: All user variants (VariantLite objects)
- `annotation_results`: Dict[rsid → AnnotationResult] with annotation JSON
- `variant_profiles`: Dict[rsid → VariantProfile] — pre-computed per-variant enrichment
- `registry`: category → {rsid: {}, gene: {}} mapping dicts
- `rsid_gene_map`: rsid → gene symbol lookup

### 5.2 Map-Driven Generation (`generate_from_maps`)

Most generators (health, drug, physical, nutrition, sports, cognitive, personality, wellness, methylation, detox) delegate to `generate_from_maps()` in `base.py`, which:

1. Iterates ALL user variants
2. For each variant with an rsid:
   a. Gets genotype, ref allele from annotations
   b. **Skips homozygous reference** (user doesn't carry risk allele)
   c. **Skips ClinVar-benign** variants (defense-in-depth)
   d. Checks rsid_map for direct match → calls `build_from_rsid()`
   e. Extracts gene/consequence → checks gene_map → calls `build_from_gene()`
3. Deduplicates by `dedup_field` (e.g., condition name)

### 5.3 Standalone Generators

- **Carrier status**: Custom logic — uses ClinVar data to discover carrier variants beyond the registry. Classifies as `affected`/`carrier`/`unaffected` based on genotype vs ref/alt alleles.
- **Rare mutations**: Finds ClinVar pathogenic variants with population frequency < 1%. Uses allele verification (including strand-flip correction).
- **Uncommon mutations**: Finds variants with functional consequences at 0.1%–5% frequency.
- **Ancestry**: Uses AIMs panel (ancestry-informative markers) with log-likelihood model across 5 super-populations.

### 5.4 Zygosity-Aware Risk Assessment

The system adjusts risk/trait levels based on genotype:
- **Homozygous reference**: De-escalate (user doesn't carry the variant)
- **Heterozygous**: Baseline level (one copy of the variant)
- **Homozygous alternate**: Escalate (two copies of the variant)

Functions: `is_homozygous_reference()`, `is_heterozygous()`, `zygosity_adjust()`

### 5.5 Pathogenicity Scoring Engine

`scoring_engine.py` aggregates evidence from all annotation sources:

| Source | Weight | Score Range |
|--------|--------|------------|
| ClinVar (API) | 0.30 | 0.0 (benign) – 1.0 (pathogenic) |
| ClinVar (local) | 0.30 | 0.0 – 1.0 |
| CADD PHRED | 0.15 | Normalized from PHRED scale |
| AlphaMissense | 0.15 | Direct am_pathogenicity value |
| gnomAD AF | 0.10 | Rarity as pathogenicity proxy |
| SIFT | 0.05 | Inverted (low = deleterious) |
| PolyPhen | 0.05 | Direct score |
| Conservation | 0.05 | PhyloP normalized |
| SpliceAI | 0.05 | Direct max score |

Classification thresholds: pathogenic ≥ 0.80, likely_pathogenic ≥ 0.60, uncertain ≥ 0.30

---

## 6. Annotation Sources

### 6.1 Local Sources (no external API calls)

| Source | File/Table | Genome Build | Lookup Method |
|--------|-----------|-------------|---------------|
| ClinVar Local | `clinvar_variants` (PG) | GRCh37/38 | rsid + allele_id |
| Ensembl VEP | `data_sources/ensembl/` VCFs → SQLite cache | GRCh38 | rsid |
| gnomAD CADD | `data_sources/gnomad/*.tsv.gz` → SQLite cache | GRCh38 | chr:pos:ref:alt |
| gnomAD-tx | `data_sources/gnomad/*tx_annotated*` (tabix) | GRCh37 | chr:pos |
| AlphaMissense | `data_sources/alpha_missense/` (tabix) | hg19/hg38 | chr:pos:ref:alt |
| 1000 Genomes | PostgreSQL import from VCF | GRCh37 | rsid, chr:pos |

### 6.2 Remote API Sources

| Source | Service File | Status |
|--------|-------------|--------|
| Ensembl REST | `genetic_api_service.py` | Available but not used for bulk |
| ClinVar NCBI | `genetic_api_service.py` | Rate-limited (10 req/s) |
| ClinPGx | `genetic_api_service.py` | Rate-limited (2 req/s) |
| SNPedia | `genetic_api_service.py` | Available |
| LitVar/PubMed | `genetic_api_service.py` | Available |

### 6.3 BigQuery Sources (optional)

ChEMBL drug mechanisms, FDA drug labels, AlphaFold protein structure — currently disabled in production.

---

## 7. Frontend Architecture

### 7.1 Component Hierarchy

```
page.tsx (SPA entry point)
├── AuthForm.tsx         — Login/register
├── FileUpload.tsx       — Drag-drop VCF/CSV upload
├── Dashboard.tsx        — Category panel orchestrator
│   ├── HealthPanel.tsx
│   ├── DrugResponsesPanel.tsx
│   ├── AncestryPanel.tsx
│   ├── CarrierPanel.tsx
│   ├── ... (13 category panels)
│   └── VariantDetailDialog.tsx  — Annotation detail overlay
├── VariantSearch.tsx    — Variant lookup interface
├── SettingsPanel.tsx    — User profile
└── AdminPanel.tsx       — Admin management
```

### 7.2 Data Flow

1. Frontend calls `GET /api/analysis/dashboard-data` with analysis ID
2. Backend queries all 14 insight tables + analysis header
3. Returns JSON blob consumed by each category panel
4. Panels render risk levels, recommendations, associated variants
5. `VariantDetailDialog` fetches detailed annotation for a specific variant

### 7.3 State Management

- No global state manager (Redux, Zustand, etc.)
- React hooks + localStorage for theme/token persistence
- Each panel fetches its own data from the shared dashboard response

---

## 8. Key Design Decisions

### 8.1 Deduplication Architecture

Genetic markers and annotations are stored globally and never deleted. When a user deletes their analysis, only `analysis_variants` and insight tables are cascade-deleted. This avoids redundant API calls for markers already seen across users.

### 8.2 Lightweight Variant Loading (VariantLite)

For analyses with 600K+ variants, the system avoids SQLAlchemy ORM overhead by loading variants as Core SQL rows into `VariantLite` dataclasses. This eliminates a 60-90 second event-loop stall from ORM materialization.

### 8.3 Shared Annotation Service

`shared_annotation_service.py` manages the annotation cache layer. Before making any external/local lookup, it checks `shared_variant_annotations` for existing data. Only missing variants trigger new lookups.

### 8.4 Variant Profiles (Single Source of Truth)

`build_variant_profiles()` runs ONCE before all generators, pre-computing:
- Effective reference allele (annotation-preferred over marker)
- Gene, consequence, impact
- Population frequency
- Zygosity classification (hom-ref, het, hom-alt)
- ClinVar significance
- Composite pathogenicity score

All generators read from profiles rather than re-extracting from raw annotation JSON.

### 8.5 Background Worker Architecture

The `worker.py` process polls for pending analyses and runs them asynchronously. The worker pre-loads all local data sources at startup (ClinVar PG, gnomAD cache, Ensembl VEP cache, 1000 Genomes) to avoid repeated initialization.

---

## 9. File Organization

### Backend Services (~35 files)

```
services/
├── analysis_service.py          # Main orchestrator (1800 LOC)
├── analysis_queue.py            # Background job queue
├── shared_annotation_service.py # Annotation cache layer
├── scoring_engine.py            # Pathogenicity scoring
├── auto_categorizer.py          # Category rules engine
├── variant_uploader.py          # VCF/CSV parsing
├── local_annotation.py          # Local source dispatch
├── clinvar_local.py             # ClinVar PG queries
├── clinvar_etl.py               # ClinVar file import
├── clinvar_direct.py            # ClinVar direct file access
├── ensembl_local.py             # Gene lookup service
├── ensembl_vep_local.py         # VEP VCF → SQLite cache
├── ensembl_vep_etl.py           # VEP ETL pipeline
├── ensembl_etl.py               # Ensembl data ETL
├── gnomad_local.py              # gnomAD PG queries
├── gnomad_cache.py              # gnomAD SQLite cache
├── gnomad_etl.py                # gnomAD file import
├── gnomad_bigquery.py           # gnomAD BigQuery access + backfill
├── gnomad_tx.py                 # gnomAD transcript annotation
├── datasource_utils.py          # Shared data source utilities (VCF parsing, cache, type coercion)
├── thousand_genomes_local.py    # 1000G PG queries
├── thousand_genomes_etl.py      # 1000G import
├── thousand_genomes_direct.py   # 1000G direct file access
├── genetic_api_service.py       # Remote API hub
├── api_endpoints.py             # API config + rate limits
├── discovery_service.py         # Auto-discovery of markers
├── insights_service.py          # Insight aggregation/API
├── knowledge_graph.py           # Variant-gene-disease graph
├── annotation_constants.py      # Annotation constants
├── job_logs.py                  # Job log collector
├── user_service.py              # User CRUD + auth
├── health_insights.py           # DEAD — legacy mock
├── drug_response.py             # DEAD — legacy mock
└── insight_generators/          # 15 files (see §5)
```

### Key Counts (from latest analysis run)

- **User variants**: 609,346 (consumer CSV)
- **Genetic markers**: 731,703 (global catalog)
- **Variant mappings**: 20,105 across 12 categories
- **ClinVar records**: 8,690,147
- **1000 Genomes records**: 112,777,885
- **Ensembl VEP cache**: 712,732 variants
- **gnomAD PG**: Empty (ETL not run), 419 in SQLite cache
- **Insights generated**: 249 per analysis
