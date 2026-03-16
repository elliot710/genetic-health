# Genetic Health Analysis Toolkit — Architecture Documentation

> **Last updated:** March 15, 2026
> **Codebase size:** ~64K LOC backend (Python), ~11K LOC frontend (TypeScript/React)
> **Database migrations:** 38 Alembic revisions

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Infrastructure & Deployment](#2-infrastructure--deployment)
3. [Backend Architecture](#3-backend-architecture)
4. [Database Architecture](#4-database-architecture)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Data Flow & Pipelines](#6-data-flow--pipelines)
7. [External Data Sources](#7-external-data-sources)
8. [Security Model](#8-security-model)
9. [Concurrency & Performance](#9-concurrency--performance)
10. [Admin & Discovery System](#10-admin--discovery-system)

---

## 1. System Overview

### What the System Does

The Genetic Health Analysis Toolkit is a full-stack web application that analyzes raw genetic data (VCF and CSV files from consumer DNA tests like 23andMe, AncestryDNA, etc.) and produces personalized health insights across 13 categories:

| Category | Table | What It Tells Users |
|----------|-------|---------------------|
| Health Risks | `health_risks` | Disease predispositions (cardiovascular, cancer, diabetes, etc.) |
| Drug Responses | `drug_responses` | Pharmacogenomic metabolism (CYP2D6, CYP2C19, DPYD, etc.) |
| Ancestry | `ancestry_results` | Population composition, haplogroups, Neanderthal variants |
| Carrier Status | `carrier_status` | Recessive condition carrier status (CF, SMA, etc.) |
| Wellness | `wellness_metrics` | Sleep quality, stress response, longevity markers |
| Methylation | `methylation_profiles` | MTHFR/COMT/MTR methylation capacity |
| Detoxification | `detoxification_profiles` | Phase I/II/III detox enzyme capacity |
| Rare Mutations | `rare_mutations` | High-impact pathogenic/likely pathogenic variants |
| Uncommon Mutations | `uncommon_mutations` | Research-grade uncommon variants (0.1%–5% frequency) |
| Physical Traits | `physical_traits` | Height, eye color, hair texture, etc. |
| Sports Performance | `sports_performance` | Endurance, power, recovery genetic advantages |
| Nutrition | `nutrition_traits` | Caffeine, lactose, alcohol metabolism |
| Cognitive/Personality | `cognitive_profiles`, `personality_traits` | Memory, processing speed, Big Five traits |

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User's Browser                           │
│  Next.js 15 SPA (React 19, Tailwind CSS 4, shadcn/ui, Recharts)│
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────────┐ │
│  │ AuthForm │ │ Upload   │ │ Progress   │ │ Dashboard (13    │ │
│  │          │ │ VCF/CSV  │ │ Loader     │ │ category panels) │ │
│  └──────────┘ └──────────┘ └────────────┘ └──────────────────┘ │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP REST (JSON)
                             │ JWT Bearer Auth
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Python)                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 7 API Routers: auth, upload, analysis, annotations,     │   │
│  │                 variants, admin, insights                │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Services: AnalysisService, GeneticAPIService,            │   │
│  │  VariantUploader, DiscoveryService, ScoringEngine,       │   │
│  │  ClinVarLocal, GnomadLocal, EnsemblLocal, 1000Genomes,  │   │
│  │  AlphaMissense, AnalysisQueue, JobLogs                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ DI Container (container.py): singletons + transients     │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
           ┌─────────────────┼──────────────────┐
           ▼                 ▼                  ▼
┌──────────────────┐ ┌────────────┐ ┌──────────────────────────┐
│  PostgreSQL 15   │ │ External   │ │ Local Data Files         │
│  (async SQLAlch- │ │ APIs       │ │                          │
│  emy 2.0 +       │ │            │ │ • AlphaMissense (tabix)  │
│  asyncpg)        │ │ • Ensembl  │ │ • ClinVar TSV/VCF (ETL) │
│                  │ │ • ClinVar  │ │ • gnomAD CADD TSV (ETL)  │
│ 25+ tables       │ │ • ClinPGx  │ │ • Ensembl VEP VCFs      │
│ ~860 LOC models  │ │ • SNPedia  │ │ • 1000 Genomes VCF (ETL)│
│                  │ │ • LitVar   │ │                          │
│                  │ │ • BigQuery │ └──────────────────────────┘
└──────────────────┘ └────────────┘
```

---

## 2. Infrastructure & Deployment

### Docker Compose Stack

Three containers orchestrated with `docker-compose.yml`:

| Service | Image | Port | Volumes | Health Check |
|---------|-------|------|---------|-------------|
| `postgres` | `postgres:15` | 5432 | Named `postgres_data` + `init-db.sql` | `pg_isready` every 10s |
| `backend` | Custom (Python 3.11-slim + UV) | 8000 | Bind mount `.:/app` (hot reload), exclude `.venv` | `curl /health` every 30s |
| `frontend` | Custom (Node.js + pnpm) | 3000 | Bind mount `./frontend:/app`, exclude `node_modules` | None |

**Startup order:** postgres (healthy) → backend → frontend

### Backend Dockerfile

- Base: `python:3.11-slim`
- System deps: `build-essential`, `curl`, `libpq-dev`, `zlib1g-dev`, `libbz2-dev`, `liblzma-dev` (for pysam tabix)
- Package manager: [UV](https://github.com/astral-sh/uv) (fast Python package installer)
- Dependency lock: `pyproject.toml` + `uv.lock` with `uv sync --frozen`
- Hot reload: `uvicorn --reload --reload-dir backend`

### Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection (asyncpg) | Yes |
| `SECRET_KEY` | JWT signing key (HS256) | Yes (has dev default) |
| `NCBI_API_KEY` | NCBI E-utilities rate limit boost (3→10 req/s) | Recommended |
| `ALPHA_MISSENSE_DATA_DIR` | Path to AlphaMissense tabix files | Optional |
| `CLINVAR_DATA_DIR` | Path to ClinVar TSV/VCF files | Optional |
| `GNOMAD_DATA_DIR` | Path to gnomAD CADD files | Optional |
| `ENSEMBL_DATA_DIR` | Path to Ensembl VEP VCF + cDNA FASTA files | Optional |
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP service account for BigQuery | Optional |
| `GEMINI_API_KEY` | Google Gemini for LLM insights | Optional |

---

## 3. Backend Architecture

### 3.1 Application Entry Point (`main.py`, ~180 LOC)

The FastAPI app initializes in this order:

1. **CORS middleware** — allows `localhost:3000`, `localhost:3001`, `127.0.0.1:3000`
2. **Router mounting** — 7 routers (auth, analysis, upload, annotations, variants, admin, insights)
3. **Startup event:**
   - `init_db()` — create all tables via SQLAlchemy
   - Install per-job log handlers on analysis-related loggers
   - Start `AnalysisQueue` processor (background task runner)
   - Detect and re-queue stale analyses (server restart recovery)
   - Pre-check 5 local data sources (ClinVar PG, gnomAD PG+BQ, 1000 Genomes, Ensembl VEP)
   - Preload Ensembl VEP cache asynchronously (background task, ~15 min)
4. **Shutdown event:** — graceful AnalysisQueue stop

### 3.2 API Layer (7 Routers, ~3500 LOC total)

| Router | Prefix | Auth Required | LOC | Key Endpoints |
|--------|--------|--------------|-----|---------------|
| `auth_routes` | `/auth` | Partial | ~130 | `POST /register`, `POST /login`, `GET /me`, `PUT /me`, `POST /change-password` |
| `upload_routes` | `/upload` | Yes | ~180 | `POST /vcf`, `POST /csv`, `DELETE /data`, `DELETE /analysis/{id}` |
| `analysis_routes` | `/api/analysis` | Yes | ~890 | `POST /start/{id}`, `GET /status/{id}`, `GET /results/{id}`, `GET /dashboard-data`, `POST /cancel`, `POST /pause`, `POST /resume` |
| `annotation_routes` | `/api/annotations` | Yes | ~980 | `POST /variant`, `POST /batch`, `POST /literature`, `POST /clinical-summary`, `GET /variant-details/{rsid}` |
| `variant_routes` | `/api/variants` | Yes | ~850 | `POST /lookup`, `GET /search`, `GET /categories` |
| `admin_routes` | `/api/admin` | Admin Only | ~350 | Users CRUD, panels CRUD, markers CRUD, discoveries approve/reject |
| `insights_routes` | `/api/insights` | Yes | ~50 | LLM insight generation (experimental) |

**Key endpoint: `GET /api/analysis/dashboard-data`** — The single endpoint that powers the entire dashboard. Returns all 13 category datasets plus summary statistics, genotype maps, and AlphaMissense/ClinVar count maps. Every panel component fetches from this endpoint.

### 3.3 Service Layer (~10K LOC)

#### Core Analysis Pipeline

| Service | File | LOC | Responsibility |
|---------|------|-----|---------------|
| `ComprehensiveAnalysisService` | `analysis_service.py` | ~2700 | Main analysis engine — annotates variants and populates all 13 insight tables |
| `SharedVariantAnnotationService` | `analysis_service.py` | ~200 | Manages shared annotation cache (dedup across users) |
| `AnalysisQueue` | `analysis_queue.py` | ~180 | Singleton background job queue with concurrency limits |
| `VariantUploader` | `variant_uploader.py` | ~150 | VCF/CSV parsing → GeneticMarker dedup + AnalysisVariant creation |
| `ScoringEngine` | `scoring_engine.py` | ~200 | Composite pathogenicity scoring from multiple data sources |
| `AutoCategorizer` | `auto_categorizer.py` | ~150 | Rule-based variant-to-category assignment |

#### Data Source Services (Local)

| Service | File | Data Source | Lookup Method |
|---------|------|------------|---------------|
| `ClinVarLocalService` | `clinvar_local.py` | PostgreSQL (`clinvar_variants` table) | rsid → aggregated clinical data |
| `GnomadLocalService` | `gnomad_local.py` | PostgreSQL (`gnomad_variants`, `gnomad_gene_constraints`) | rsid or (chr,pos,ref,alt) → population frequencies |
| `EnsemblLocalService` | `ensembl_local.py` | PostgreSQL (`ensembl_genes`) | gene_symbol or (chr,pos) → gene info |
| `ThousandGenomesService` | `thousand_genomes_local.py` | PostgreSQL (`thousand_genomes_variants`) | rsid → superpopulation frequencies |
| `EnsemblVEPService` | `ensembl_vep_local.py` | PostgreSQL (`ensembl_vep_variants`) | rsid → VEP consequences (pre-cached from VCF) |
| `AlphaMissenseService` | `utils/alpha_missense.py` | Tabix-indexed TSV files (pysam) | (chr,pos,ref,alt) → AI pathogenicity prediction |

#### Data Source Services (Remote)

| Service | File | APIs Called | Rate Limits |
|---------|------|------------|-------------|
| `OptimizedGeneticAPIService` | `genetic_api_service.py` | Ensembl VEP, ClinVar, ClinPGx, SNPedia, LitVar | Per-endpoint (1–15 req/s) |
| `GnomadBigQueryService` | `gnomad_bigquery.py` | Google BigQuery (gnomAD, ChEMBL, FDA Drug, AlphaFold) | GCP quotas |

#### Support Services

| Service | File | Purpose |
|---------|------|---------|
| `DiscoveryService` | `discovery_service.py` | Auto-discover new panel markers from user lookups |
| `HealthInsights` | `health_insights.py` | Legacy health risk assessment (being phased out) |
| `DrugResponseAnalyzer` | `drug_response.py` | Legacy pharmacogenomics (being phased out) |
| `JobLogCollector` | `job_logs.py` | Per-analysis in-memory log collection (contextvars-tracked) |
| `VCFParser` | `utils/vcf_parser.py` | Parse VCF/CSV files from multiple providers (23andMe, AncestryDNA, etc.) |
| `VariantRegistry` | `variant_registry.py` | Static rsid→condition maps (being replaced by VariantMapping table) |

### 3.4 Dependency Injection (`core/container.py`, ~180 LOC)

Custom lightweight DI container with three registration modes:

- **Singleton** — One instance shared globally (e.g., `HealthInsights`, `DrugResponseAnalyzer`)
- **Factory** — Created once on first `get()`, then cached (promoted to singleton)
- **Transient** — New instance on every `get()` call (e.g., `OptimizedGeneticAPIService` — avoids shared in-memory cache leaking between users)

Lifecycle methods: `initialize_async_services()`, `cleanup()` — iterate over singletons calling `.initialize()` / `.close()`.

### 3.5 Configuration (`core/config.py`)

Three configuration classes:

- **`APIConfiguration`** — base_delay, max_retries, timeout (30s), batch_size, max_concurrent
- **`AnalysisConfiguration`** — batch_size, max_variants_per_batch (20), processing_timeout (1h), progress_update_interval (5s)
- **`DatabaseConfiguration`** — max_connections (20), pool timeouts, pool recycling

All loaded from environment variables with sensible defaults via `Settings` class.

### 3.6 Exception Hierarchy

```
GeneticAnalysisException (base)
├── AnalysisNotFoundException
├── VariantProcessingException
├── AnalysisTimeoutException
├── InvalidVariantException
├── SpecializedAnalysisException
├── DatabaseException
└── APIServiceException
    ├── APIRateLimitException
    ├── APIConnectionException
    └── APIResponseException
```

---

## 4. Database Architecture

### 4.1 Overview

PostgreSQL 15 with async SQLAlchemy 2.0 + asyncpg driver. Connection pool: 20 base + 40 overflow (60 max), 30-minute recycle, pre-ping enabled.

**38 Alembic migrations** track the schema evolution from initial user/analysis tables through the full deduplication architecture, local data ETL tables, admin config, and discovery system.

### 4.2 Entity-Relationship Diagram

```
┌──────────┐       ┌──────────────────┐       ┌──────────────────┐
│  users   │──1:N──│ genetic_analyses │──1:N──│ analysis_variants│
│          │       │                  │       │                  │
│ id       │       │ id               │  ┌───▶│ id               │
│ email    │       │ user_id (FK)     │  │    │ analysis_id (FK) │─── CASCADE DELETE
│ username │       │ filename         │  │    │ marker_id (FK)   │───┐
│ password │       │ file_type        │  │    │ genotype         │   │
│ is_admin │       │ analysis_status  │  │    │ quality          │   │
│ avatar   │       │ progress_%      │  │    └──────────────────┘   │
└──────────┘       │ total_variants   │  │                          │
                   │ current_step     │  │    ┌──────────────────┐   │
                   └──────────────────┘  │    │ genetic_markers  │◀──┘
                                         │    │ (NEVER DELETED)  │
                   ┌─────────────────┐   │    │                  │
                   │ variant_        │   │    │ id               │
                   │ annotations     │───┘    │ rsid (unique)    │
                   │                 │        │ chromosome       │
                   │ analysis_id(FK) │─CASCADE│ position         │
                   │ shared_ann_id   │──┐     │ ref/alt alleles  │
                   │ rsid            │  │     │ upload_count     │
                   │ user_notes      │  │     └──────┬───────────┘
                   └─────────────────┘  │            │ 1:1
                                        │     ┌──────▼───────────┐
                                        │     │ shared_variant_  │
                                        └────▶│ annotations      │
                                              │ (NEVER DELETED)  │
                                              │                  │
                                              │ marker_id (FK)   │
                                              │ rsid             │
                                              │ ensembl_data     │
                                              │ clinvar_data     │
                                              │ pharmgkb_data    │
                                              │ snpedia_data     │
                                              │ litvar_data      │
                                              │ alpha_missense   │
                                              │ clinvar_local    │
                                              │ gnomad_data      │
                                              │ 1000genomes_data │
                                              │ chembl_data      │
                                              │ fda_drug_data    │
                                              │ alphafold_data   │
                                              │ usage_count      │
                                              │ failed_sources   │
                                              └──────────────────┘
```

### 4.3 Table Catalog

#### Core User & Analysis Tables

| Table | Rows (typical) | Deletion Policy | Purpose |
|-------|---------------|----------------|---------|
| `users` | Tens | Standard | User accounts with admin/verified flags |
| `genetic_analyses` | Per-user (1-5) | User-deletable | Analysis jobs with progress tracking |

#### Deduplication Layer (Key Design Decision)

The deduplication architecture is the most important architectural decision in the system. It ensures that:
1. **Genetic markers are global** — `genetic_markers` stores every unique variant (by rsid) ever uploaded. Never deleted. `upload_count` tracks reuse.
2. **Annotations are shared** — `shared_variant_annotations` caches all external API responses per variant. Never deleted. `usage_count` tracks how many analyses reference each annotation.
3. **User data is isolated** — `analysis_variants` links a user's analysis to global markers with their specific genotype. Cascade-deleted with the analysis.
4. **API calls are minimized** — If variant rs7903146 was already annotated for User A, User B's analysis reuses the cached annotation instead of making redundant API calls.

| Table | Rows (typical) | Deletion Policy | Purpose |
|-------|---------------|----------------|---------|
| `genetic_markers` | 500K–1M+ | **Never deleted** | Global variant catalog (rsid, chr, pos, alleles) |
| `analysis_variants` | Per-analysis (600K+) | CASCADE with analysis | Links analysis → marker + user genotype |
| `shared_variant_annotations` | 500K–1M+ | **Never deleted** | Cached external API responses (12 JSON columns) |
| `variant_annotations` | Per-analysis | CASCADE with analysis | User-specific references to shared annotations |

#### Insight Tables (13 categories, all CASCADE-delete)

| Table | Fields | Key Data |
|-------|--------|----------|
| `health_risks` | condition, risk_level, risk_score, recommendations | Disease predispositions |
| `drug_responses` | gene, drug, response_type, recommendations | Pharmacogenomic metabolism |
| `ancestry_results` | population, percentage, composition (JSON), haplogroups (JSON) | Ancestry breakdown |
| `carrier_status` | condition, carrier_status, inheritance_pattern | Recessive carrier info |
| `wellness_metrics` | metric_name, genetic_predisposition, optimization_score | Wellness markers |
| `methylation_profiles` | gene, variant, methylation_capacity, supplements | Methylation pathways |
| `detoxification_profiles` | detox_phase, gene, detox_capacity, toxin_sensitivity | Detox enzymes |
| `rare_mutations` | gene, mutation_type, clinical_significance, penetrance, disease_association | High-impact variants |
| `uncommon_mutations` | gene, mutation_type, effect_size, population_frequency, research_status | Research-grade variants |
| `physical_traits` | trait_name, trait_category, genetic_result, confidence | Physical characteristics |
| `sports_performance` | performance_category, genetic_advantage, sport_recommendations | Athletic traits |
| `nutrition_traits` | nutrient, metabolism_type, sensitivity_level | Nutrient metabolism |
| `cognitive_profiles` | cognitive_domain, genetic_score, percentile | Cognitive abilities |
| `personality_traits` | trait_name, genetic_tendency, confidence_level | Big Five personality |

#### Local Data Source Tables (ETL-imported)

| Table | Rows (typical) | Source | Purpose |
|-------|---------------|--------|---------|
| `clinvar_variants` | ~2.5M | ClinVar TSV + VCF | Clinical significance, gene, conditions |
| `clinvar_gene_conditions` | ~30K | ClinVar gene_condition_source_id.txt | Gene→disease associations |
| `clinvar_gene_stats` | ~10K | ClinVar gene_specific_summary.txt | Per-gene submission stats |
| `gnomad_variants` | ~1M+ | gnomAD CADD TSV + BigQuery | Population frequencies, CADD scores, functional predictions |
| `gnomad_gene_constraints` | ~20K | gnomAD constraint data | pLI, LOEUF, missense Z-scores |
| `ensembl_genes` | ~60K | Ensembl cDNA/ncRNA FASTA headers | Gene models (chr, start, end, biotype) |
| `ensembl_vep_variants` | ~50K+ | Ensembl VEP VCF dumps | Pre-computed VEP consequences |
| `thousand_genomes_variants` | ~80M+ | Ensembl 1000G Phase 3 VCF | Superpopulation allele frequencies |

#### Configuration & Admin Tables

| Table | Purpose |
|-------|---------|
| `panel_marker_configs` | Maps rsids to dashboard panels (admin-managed) |
| `variant_mappings` | rsid→condition and gene→trait mappings (replaces static registry) |
| `category_rules` | Auto-categorization rules (ClinVar significance, gene lists, consequence types) |
| `annotation_source_configs` | Enable/disable external API sources |
| `pending_discoveries` | Auto-discovered markers awaiting admin approval |
| `variant_lookup_cache` | External lookup response cache with usage counting |

### 4.4 Indexing Strategy

**Primary indexes (B-tree):**
- `genetic_markers.rsid` (unique) — variant dedup lookup
- `genetic_markers(chromosome, position)` — positional queries
- `shared_variant_annotations.rsid` (unique) — annotation cache lookup
- `shared_variant_annotations.marker_id` (unique) — FK join
- `analysis_variants(analysis_id, marker_id)` — per-analysis variant access
- `clinvar_variants.rsid` + `(rsid, allele_id)` — ClinVar lookup
- `gnomad_variants.rsid` + `(chrom, pos, ref, alt)` — gnomAD lookup
- `ensembl_vep_variants.rsid` (unique) — VEP cache
- `thousand_genomes_variants.rsid` + `(chrom, pos)` — 1000G lookup

**Unique constraints:**
- `variant_annotations(analysis_id, analysis_variant_id)` — prevent duplicate user annotations
- `panel_marker_configs(panel_id, rsid)` — prevent duplicate panel markers
- `variant_mappings(category, map_type, key)` — prevent duplicate mappings

---

## 5. Frontend Architecture

### 5.1 Technology Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| Next.js | 15+ | React framework (App Router, Turbopack) |
| React | 19 | UI library |
| TypeScript | 5+ | Type safety |
| Tailwind CSS | 4 | Utility-first styling |
| shadcn/ui | Latest | Radix-based component primitives (17 components) |
| Recharts | 2.x | Data visualization (11 chart types) |
| Framer Motion | — | Animations |
| Lucide React + Tabler Icons | — | Iconography |
| react-simple-maps | — | World map (ancestry panel) |
| react-dropzone | — | File drag-and-drop |

### 5.2 Application Flow (SPA)

The frontend is a **single-page application** using Next.js App Router but without client-side routing. All navigation is hash-based within `page.tsx`:

```
┌──────────────┐     ┌───────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   AuthForm   │────▶│  FileUpload   │────▶│ AnalysisProgress│────▶│    Dashboard     │
│              │     │               │     │   Loader        │     │  (13 panels)     │
│ Login or     │     │ Drag-drop     │     │                 │     │                  │
│ Register     │     │ VCF/CSV       │     │ Polls /status   │     │ Hash-based nav:  │
│              │     │               │     │ every 2s        │     │ #health, #drugs  │
│ POST /auth/  │     │ POST /upload/ │     │                 │     │ #ancestry, etc.  │
│ login        │     │ {vcf|csv}     │     │ On complete:    │     │                  │
│   → token    │     │   → analysis  │     │ GET /dashboard  │     │ GET /dashboard   │
│              │     │     _id       │     │     -data       │     │   -data          │
└──────────────┘     └───────────────┘     └─────────────────┘     └──────────────────┘
```

**State management:** React hooks + localStorage. No global state manager (Redux, Zustand, etc.).

- `token` — JWT stored in localStorage
- `isDarkMode` — boolean in localStorage, synced to `<html class="dark">`
- `analysisData` — fetched from `/api/analysis/dashboard-data`

### 5.3 Component Hierarchy

```
app/page.tsx  (SPA orchestrator, ~360 LOC)
├── AuthForm.tsx  (login/register, ~300 LOC)
├── FileUpload.tsx  (drag-drop upload, ~280 LOC)
├── AnalysisProgressLoader.tsx  (progress polling, ~250 LOC)
└── Dashboard.tsx  (dashboard orchestrator, ~1900 LOC)
    ├── Overview tab
    │   ├── GenomicCharts.tsx  (11 chart types, ~600 LOC)
    │   ├── VariantSearch.tsx  (variant lookup, ~450 LOC)
    │   ├── SmartInsights.tsx  (LLM insights, experimental)
    │   └── KnowledgeGraph.tsx  (graph viz, experimental)
    ├── 13 Category Panels  (each ~250-500 LOC)
    │   ├── HealthPanel.tsx
    │   ├── DrugResponsesPanel.tsx
    │   ├── AncestryPanel.tsx  (with world map)
    │   ├── CarrierStatusPanel.tsx
    │   ├── WellnessPanel.tsx
    │   ├── MethylationPanel.tsx
    │   ├── DetoxPanel.tsx
    │   ├── RareMutationsPanel.tsx
    │   ├── UncommonMutationsPanel.tsx
    │   ├── PhysicalTraitsPanel.tsx
    │   ├── SportsPanel.tsx
    │   ├── FoodNutritionPanel.tsx
    │   ├── IntelligencePanel.tsx
    │   └── PersonalityPanel.tsx
    ├── SettingsPanel.tsx  (profile management, ~250 LOC)
    ├── AdminPanel.tsx  (admin CRUD, ~800 LOC)
    └── Shared utilities
        ├── categories/shared.tsx  (shared components + severity mappers, ~500 LOC)
        ├── categories/types.ts  (TypeScript interfaces, ~200 LOC)
        ├── categories/VariantDetailDialog.tsx  (annotation modal, ~400 LOC)
        └── categories/ResearchLinks.tsx  (external database links)
```

### 5.4 Theme System (`utils/theme.ts`, ~400 LOC)

Centralized dark/light mode with glassmorphism design:

- `getTheme(isDarkMode)` — Returns comprehensive theme object (backgrounds, text colors, gradients, status colors, category colors, form styles)
- `getThemeClass(baseClass, isDarkMode)` — Maps 100+ Tailwind class variants between light and dark modes
- CSS variables defined in `globals.css` using oklch color space

### 5.5 Shared Panel Components (`categories/shared.tsx`)

Reusable building blocks for all 13 category panels:

| Component | Purpose |
|-----------|---------|
| `CategoryHeader` | Panel title with item count badge |
| `EmptyState` | No-data display with icon and message |
| `SectionCard` | Card wrapper for panel sections |
| `StatusBadge` | Severity-colored badge (danger/warning/success/info/neutral) |
| `ScoreBar` | Progress bar with label and percentage |
| `VariantLinks` | Inline links to dbSNP, ClinVar, SNPedia, Ensembl, PubMed |
| `ClickableRsidBadge` | Badge that opens variant detail dialog |
| `MasonryLayout` | Responsive grid wrapper |
| `DisclaimerCard` | Medical/research disclaimer |

**Severity mappers** (consistent UX across panels): `riskToSeverity()`, `capacityToSeverity()`, `advantageToSeverity()`, `sensitivityToSeverity()`, `clinicalSignificanceToSeverity()`, `carrierStatusToSeverity()`

### 5.6 API Integration Pattern

All API calls use direct `fetch()` — no API client abstraction:

```typescript
const response = await fetch('http://localhost:8000/api/endpoint', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});
const data = await response.json();
```

**Error handling:** Most panel data fetches catch errors silently (console.log only). User-facing errors shown in auth, upload, and settings forms.

### 5.7 UI Component Library

17 shadcn/ui components (Radix primitives): `button`, `card`, `dialog`, `badge`, `input`, `label`, `select`, `tabs`, `table`, `switch`, `scroll-area`, `separator`, `tooltip`, `dropdown-menu`, `sheet`, `sidebar`, `skeleton`.

---

## 6. Data Flow & Pipelines

### 6.1 Upload Pipeline

```
User drops VCF/CSV file
     │
     ▼
POST /upload/{vcf|csv}
     │
     ├──1. Create GeneticAnalysis (status='processing')
     ├──2. VCFParser.parse_vcf_content(file_bytes)
     │     ├── Auto-detect format (VCF vs CSV)
     │     ├── Handle multiple provider formats (23andMe, AncestryDNA, etc.)
     │     └── Return List[{rsid, chr, pos, ref, alt, genotype, quality, filter}]
     ├──3. VariantUploader.upload_variants(analysis_id, variants)
     │     ├── Batch 500 variants at a time
     │     ├── UPSERT into genetic_markers (ON CONFLICT rsid → upload_count+1, merge alts)
     │     ├── INSERT into analysis_variants (link analysis → marker + genotype)
     │     └── Return (processed_count, new_markers_created)
     └──4. Update GeneticAnalysis.total_variants
```

### 6.2 Analysis Pipeline (Background Processing)

```
POST /api/analysis/start/{id}
     │
     ▼
AnalysisQueue.enqueue_analysis(id, user_id)
     │  (max 3 global jobs, max 2 per user)
     ▼
ComprehensiveAnalysisService.process_analysis(analysis_id)
     │
     ├── Phase 1: Gene Map (0-2%)
     │   └── Build rsid→gene map from Ensembl VEP local + Ensembl gene lookup
     │
     ├── Phase 2: Annotation (2-30%)
     │   ├── Load all AnalysisVariants for this analysis
     │   ├── Extract RSIDs → check SharedVariantAnnotation cache
     │   ├── REUSE existing annotations (increment usage_count)
     │   ├── For new RSIDs: batch call external APIs
     │   │   ├── Ensembl VEP REST (or local VEP cache)
     │   │   ├── ClinVar API (or local ClinVar PG)
     │   │   ├── ClinPGx API
     │   │   ├── SNPedia MediaWiki API
     │   │   └── LitVar/PubMed API
     │   ├── For each annotation: also lookup local sources
     │   │   ├── AlphaMissense (tabix)
     │   │   ├── ClinVar Local (PG)
     │   │   ├── gnomAD Local (PG, local_only=True during bulk)
     │   │   └── 1000 Genomes (PG)
     │   ├── UPSERT into SharedVariantAnnotation (ON CONFLICT → backfill NULLs)
     │   └── CREATE VariantAnnotation references for this analysis
     │
     ├── Phase 3: BigQuery Enrichment (30-90%)
     │   ├── gnomAD BigQuery (population frequencies)
     │   ├── ChEMBL (drug mechanisms)
     │   ├── FDA Drug Labels (CYP interactions)
     │   └── AlphaFold (protein structure confidence)
     │
     └── Phase 4: Insight Generation (90-100%)
         ├── Compute pathogenicity scores (ScoringEngine)
         ├── Apply category rules (CategoryRule table + AutoCategorizer)
         ├── Populate all 13 insight tables:
         │   ├── health_risks (from ClinVar pathogenic + gene-disease associations)
         │   ├── drug_responses (from ClinPGx + CYP gene data)
         │   ├── ancestry_results (from 1000G population frequencies)
         │   ├── carrier_status (from ClinVar recessive conditions)
         │   ├── rare_mutations (from ClinVar pathogenic + AlphaMissense)
         │   ├── uncommon_mutations (from gnomAD frequency 0.1-5%)
         │   ├── methylation_profiles (from MTHFR/COMT variant mappings)
         │   ├── detoxification_profiles (from CYP/GST/NAT variant mappings)
         │   ├── physical_traits (from trait-associated variant mappings)
         │   ├── sports_performance (from ACTN3/ACE variant mappings)
         │   ├── nutrition_traits (from MCM6/ADH1B variant mappings)
         │   ├── cognitive_profiles (from BDNF/COMT variant mappings)
         │   └── personality_traits (from 5-HTTLPR/OXTR variant mappings)
         └── Update GeneticAnalysis (status='completed', progress=100%)
```

### 6.3 Progress Tracking

Four-phase model with time-based weights:

| Phase | Range | Weight | Duration | Activity |
|-------|-------|--------|----------|----------|
| 1 | 0–2% | 2% | Seconds | Gene map building |
| 2 | 2–30% | 28% | Minutes | Variant annotation (API calls) |
| 3 | 30–90% | 60% | Minutes–hours | BigQuery enrichment |
| 4 | 90–100% | 10% | Seconds–minutes | Insight table population |

Frontend polls `GET /api/analysis/status/{id}` every 2 seconds. Status values: `pending`, `processing`, `completed`, `failed`, `paused`, `stopped`.

### 6.4 Deletion Pipeline

When user deletes their data:

1. **Instant:** Mark analysis as `status='deleted'` (immediate UI feedback)
2. **Background:** Batched deletes (50K rows at a time):
   - `variant_annotations` → `analysis_variants` → all 13 insight tables
   - Uses CASCADE on `analysis_variants` for `variant_annotations`
3. **Preserved:** `genetic_markers` and `shared_variant_annotations` are **never deleted** — they serve as the global cache

---

## 7. External Data Sources

### 7.1 Remote APIs

| API | Service | Rate Limit | Data Retrieved | Cache |
|-----|---------|-----------|----------------|-------|
| **Ensembl VEP** | `genetic_api_service.py` | 15 req/s | Variant consequences, gene, transcript, impact | SharedVariantAnnotation.ensembl_data |
| **ClinVar** (NCBI) | `genetic_api_service.py` | 10 req/s (with key) | Clinical significance, conditions, review status | SharedVariantAnnotation.clinvar_data |
| **ClinPGx** | `genetic_api_service.py` | 1 req/s | Drug-gene associations, dosing guidelines | SharedVariantAnnotation.pharmgkb_data |
| **SNPedia** | `genetic_api_service.py` | 2 req/s | Community-curated variant descriptions | SharedVariantAnnotation.snpedia_data |
| **LitVar/PubMed** | `genetic_api_service.py` | 10 req/s | Research publications, variant mentions | SharedVariantAnnotation.litvar_data |
| **Google BigQuery** | `gnomad_bigquery.py` | GCP quotas | gnomAD frequencies, ChEMBL, FDA Drug, AlphaFold | SharedVariantAnnotation.{gnomad,chembl,fda_drug,alphafold}_data |

### 7.2 Local Data Sources

| Source | Storage | Size | Lookup Method |
|--------|---------|------|---------------|
| **ClinVar** (TSV+VCF) | PostgreSQL `clinvar_variants` | ~2.5M rows | rsid, gene, significance index |
| **gnomAD** (CADD TSV) | PostgreSQL `gnomad_variants` | ~1M+ rows | rsid, (chrom,pos,ref,alt) index |
| **gnomAD Constraints** | PostgreSQL `gnomad_gene_constraints` | ~20K rows | gene index |
| **Ensembl Genes** | PostgreSQL `ensembl_genes` | ~60K rows | gene_symbol, (chr,start,end) index |
| **Ensembl VEP** | PostgreSQL `ensembl_vep_variants` | ~50K+ rows | rsid unique index |
| **1000 Genomes** | PostgreSQL `thousand_genomes_variants` | ~80M+ rows | rsid, (chrom,pos) index |
| **AlphaMissense** | Tabix-indexed TSV (pysam) | ~71M predictions | (chrom,pos,ref,alt) tabix query |

### 7.3 Data Source Priority

During analysis, the system prefers local sources over remote APIs:

1. **Check local first:** ClinVar PG, gnomAD PG, Ensembl VEP PG, 1000 Genomes PG
2. **Fall back to remote:** If local is empty or variant not found
3. **BigQuery fallback:** gnomAD, ChEMBL, FDA Drug, AlphaFold (deferred to Phase 3)
4. **AlphaMissense:** Always local (tabix files), no remote API

---

## 8. Security Model

### 8.1 Authentication

- **JWT (HS256)** with 10-day expiry (`ACCESS_TOKEN_EXPIRE_MINUTES = 14400`)
- **bcrypt** password hashing
- **Bearer token** in `Authorization` header for all protected routes
- **`get_current_user`** dependency on all routes except `/auth/login`, `/auth/register`, `/health`

### 8.2 Authorization

- **Regular users:** Access their own analyses, variants, and profile
- **Admin users:** `is_admin=True` flag — access to admin panel (user management, panel config, discovery approval)
- **Admin check:** `admin_routes.py` verifies `current_user.is_admin` on every endpoint

### 8.3 Input Validation

- Pydantic schemas for all request bodies
- File type validation on upload (VCF, CSV, TXT only)
- Avatar size limit (500KB max, data URI validation)
- CORS restricted to `localhost:3000`, `localhost:3001`, `127.0.0.1:3000`

### 8.4 Data Isolation

- All analysis data is user-scoped (filtered by `user_id` in queries)
- Admin endpoints require `is_admin=True`
- Shared annotations are read-only to users (no direct mutation endpoints)

---

## 9. Concurrency & Performance

### 9.1 Analysis Queue

```python
AnalysisQueue:
  max_concurrent_jobs = 3  (global)
  max_per_user = 2         (per user)
  queue = asyncio.Queue    (FIFO)
```

- Background processor runs continuously after startup
- Stale analyses (left in 'processing' state) automatically re-queued on restart
- Users can pause, resume, and cancel analyses

### 9.2 API Rate Limiting

Per-endpoint rate limiters using asyncio.Lock + sleep:

| API | Rate (req/s) |
|-----|-------------|
| NCBI/ClinVar | 10.0 (with API key) |
| Ensembl | 15.0 |
| ClinPGx | 1.0 |
| SNPedia | 2.0 |
| LitVar | 10.0 |

Exponential backoff on HTTP 429 responses.

### 9.3 Connection Pooling

- **PostgreSQL:** 20 base + 40 overflow (60 max), 30s timeout, pre-ping
- **HTTP (aiohttp):** 20 connections max, 5 per host, DNS caching (300s TTL)

### 9.4 Caching Layers

| Layer | Scope | TTL | Purpose |
|-------|-------|-----|---------|
| `shared_variant_annotations` | Per-variant (global) | Permanent | API response cache across users |
| `variant_lookup_cache` | Per-variant (global) | Permanent | External lookup response cache |
| API response cache (in-memory) | Per-service instance | 1 hour | Short-term dedup within analysis run |
| Ensembl VEP cache (PG) | Global | Permanent | Pre-loaded VEP consequences |

### 9.5 Batch Processing

- **Variant upload:** 500 variants per batch (UPSERT)
- **Annotation lookup:** 500 RSIDs per batch (IN query)
- **Annotation save:** UPSERT with ON CONFLICT backfill
- **Deletion:** 50,000 rows per batch (background)
- **usage_count updates:** 30,000 RSIDs per batch (under PG parameter limit)

### 9.6 Per-Job Logging

`JobLogCollector` uses Python `contextvars` to track which asyncio task belongs to which analysis. Each analysis stores up to 500 log entries in memory (max 50 concurrent jobs tracked).

---

## 10. Admin & Discovery System

### 10.1 Admin Panel

Admin users (`.is_admin=True`) access the admin panel through the dashboard. Five management tabs:

1. **Users** — List users, toggle admin/active/verified status, create/delete accounts
2. **Panels** — Configure which markers appear in each dashboard panel (`panel_marker_configs`)
3. **Markers** — Global marker catalog management
4. **Variant Mappings** — rsid→condition and gene→trait mappings (`variant_mappings`)
5. **Pending Discoveries** — Review and approve/reject auto-discovered markers

### 10.2 Auto-Discovery Pipeline

When users perform variant lookups (`POST /api/variants/lookup`), the system:

1. Analyzes the response data (gene, consequence, clinical significance)
2. Infers which dashboard panels the variant belongs to
3. Creates `PendingDiscovery` records for admin approval
4. Admins review, approve, or reject with reason

**Inference logic** uses:
- `GENE_CATEGORY_MAP` — known gene→category mappings (MTHFR→cardiovascular, CYP2D6→pharmacogenomic)
- `CONSEQUENCE_PANEL_MAP` — consequence→category (frameshift→health)
- `DRUG_CATEGORY_MAP` — drug→subcategory (warfarin→anticoagulants)

### 10.3 Category Rules Engine

`CategoryRule` table provides configurable rules for auto-assigning variants to categories:

| Rule Type | Example | Target |
|-----------|---------|--------|
| `clinvar_significance` | `Pathogenic` | health risks |
| `clinvar_condition_keyword` | `cancer` | health risks |
| `gene_list` | `CYP2D6,CYP2C19` | drug responses |
| `molecular_consequence` | `missense_variant` | health risks |
| `am_class` | `pathogenic` | rare mutations |
| `am_score_above` | `0.564` | uncommon mutations |
| `origin` | `germline` | carrier status |

Rules evaluated in priority order (lower number = higher priority).

---

## Appendix A: File-Level Summary

### Backend Files (by LOC)

| File | LOC | Purpose |
|------|-----|---------|
| `services/analysis_service.py` | 2,698 | Main analysis engine |
| `api/annotation_routes.py` | 979 | Variant annotation endpoints |
| `api/analysis_routes.py` | 892 | Analysis lifecycle endpoints |
| `services/genetic_api_service.py` | 867 | Multi-API orchestrator |
| `api/variant_routes.py` | 853 | Variant search + lookup |
| `db/models.py` | 835 | All ORM models |
| `services/clinvar_local.py` | ~450 | ClinVar PostgreSQL service |
| `services/gnomad_local.py` | ~480 | gnomAD PostgreSQL service |
| `utils/alpha_missense.py` | ~300 | AlphaMissense tabix lookups |
| `api/admin_routes.py` | ~350 | Admin management endpoints |
| `services/api_endpoints.py` | ~350 | Endpoint configuration |
| `services/discovery_service.py` | ~300 | Auto-discovery pipeline |

### Frontend Files (by LOC)

| File | LOC | Purpose |
|------|-----|---------|
| `components/Dashboard.tsx` | 1,900 | Dashboard orchestrator |
| `components/categories/GenomicCharts.tsx` | ~600 | Chart library (11 types) |
| `components/categories/shared.tsx` | ~500 | Shared components + utilities |
| `components/categories/AncestryPanel.tsx` | ~500 | Ancestry + world map |
| `components/VariantSearch.tsx` | ~450 | Variant search interface |
| `components/categories/CarrierStatusPanel.tsx` | ~450 | Carrier status display |
| `utils/theme.ts` | ~400 | Centralized theme system |
| `components/categories/VariantDetailDialog.tsx` | ~400 | Annotation modal |
| `components/admin/AdminPanel.tsx` | ~800 | Admin CRUD interface |
| `app/page.tsx` | ~360 | SPA entry point |
