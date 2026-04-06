# Genetic Health Analysis Toolkit

A full-stack genetic data analysis platform providing personalized health insights from VCF and CSV genetic data. Everything runs in Docker with hot reload.

The source code should follow clean code Architecture.
The source code should include Unit tests for all the logical parts, with all the 3rd party or API calls being mocked. 
The source code should not include any documentations or md files. Comments should only be used in exceptional cases. The code should be self explanatory.
Do not try anything more than 3 times, if you cannot find the solution or in a loop for 3 times, ask for feedback.
Do not praise me or apologize, just be clear and respond with simple responses.
Always do plan first and only after do start with the implementations. 
Do not add logs and debugs everwhere, those should be used and implemented with the confirmation only. if you added any debugging logs, clean up after the final iterations.
All the variables should have a meaningful names. 
Methods should not be longer than 30 lines of codes, and each class should not be longer than 300 lines of code.
If you need to convert anything, use extensions and utils.
We will use eependency injection with proper namings. 

## Quick Reference

**Server**: 
IP: 204.168.200.44
ssh key: ~/.ssh/id_ed25519
user: root
DO NOT deploy unless specifically told to do it.

**Login field**: `username` (not `email`) — POST `/auth/login` takes `{"username": "...", "password": "..."}`

## Architecture

```
data_sources/               # Local data sources. available only on the production server
│   ├── 1000G/
│   ├── alpha_missense/
│   ├── clinvar/
│   ├── ensembl/
│   └── gnomad/

backend/
├── main.py                 # FastAPI app, CORS, router mounts, startup/shutdown
├── api/                    # Route handlers (7 routers)
│   ├── auth_routes.py      # /auth — register, login, me, change-password
│   ├── upload_routes.py    # /upload — VCF/CSV upload, delete data
│   ├── analysis_routes.py  # /api/analysis — start, status, results, dashboard-data
│   ├── annotation_routes.py# /api/annotations — variant details, clinical summary, literature
│   ├── variant_routes.py   # /api/variants — cached multi-source lookup
│   ├── admin_routes.py     # /api/admin — users, panels, markers, discoveries
│   └── health_routes.py    # /health — health check
├── services/               # Business logic
│   ├── analysis_service.py # Main analysis engine (ComprehensiveAnalysisService)
│   ├── variant_registry.py # Single source of truth for rsid→condition and gene→condition maps
│   ├── genetic_api_service.py # Multi-API hub (NCBI, Ensembl, ClinPGx, ClinVar, SNPedia, LitVar)
│   ├── api_endpoints.py    # Centralized endpoint config + rate limits
│   ├── analysis_queue.py   # Background task processing (singleton queue)
│   ├── variant_uploader.py # VCF/CSV parsing, marker deduplication
│   ├── discovery_service.py# Auto-discovery of new panel markers
│   ├── drug_response.py    # Pharmacogenomic data processing
│   ├── health_insights.py  # Clinical significance & health risk assessment
│   └── user_service.py     # User CRUD, authentication
├── core/
│   ├── config.py           # API/analysis/DB settings
│   ├── auth.py             # JWT HS256, 10-day expiry, bcrypt
│   ├── container.py        # DI container with singletons & factories
│   └── exceptions.py       # Custom exception classes
├── db/
│   ├── database.py         # Async SQLAlchemy 2.0 engine + session factory
│   ├── models.py           # All ORM models (see Database section)
│   └── schemas.py          # Pydantic request/response models
└── utils/

frontend/src/
├── app/
│   ├── layout.tsx          # Root layout
│   ├── page.tsx            # SPA entrypoint: Auth → Upload → Dashboard flow
│   └── globals.css
├── components/
│   ├── Dashboard.tsx        # Orchestrates all category panels + navigation
│   ├── AuthForm.tsx         # Login/register with theme toggle
│   ├── FileUpload.tsx       # Drag-drop VCF/CSV upload with progress
│   ├── VariantSearch.tsx    # Variant lookup interface
│   ├── SettingsPanel.tsx    # User profile & preferences
│   ├── categories/          # 13 specialized panels + shared utilities
│   │   ├── shared.tsx       # Reusable components: CategoryHeader, SectionCard, VariantLinks, VariantDetailDialog
│   │   ├── types.ts         # TypeScript interfaces for all panels
│   │   ├── HealthPanel.tsx, DrugResponsesPanel.tsx, AncestryPanel.tsx, ...
│   │   └── VariantDetailDialog.tsx # Annotation detail overlay
│   ├── ui/                  # shadcn/ui primitives (button, dialog, card, badge, ...)
│   └── admin/AdminPanel.tsx
├── utils/theme.ts           # Centralized glassmorphism theme (dark/light)
├── hooks/use-mobile.ts
└── lib/utils.ts             # cn() utility (clsx + tailwind-merge)
```

## Development Workflow

### Running (Docker — preferred)
```bash
docker compose up          # All 3 services with hot reload
docker compose up --build  # Rebuild after dependency changes
```

### Running (Local — if needed)
```bash
# Backend (from project root)
cd backend && PYTHONPATH=.. uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm run dev  # uses Turbopack
```

### Database Migrations
```bash
alembic upgrade head                             # Apply all migrations
alembic revision --autogenerate -m "description" # Create migration
```

### VS Code Tasks
- **"Start Both Servers"** — run from Command Palette → "Tasks: Run Task"

### Useful Docker Commands
```bash
# Run Python in backend container
docker exec dna_toolkit-backend-1 uv run python -c "..."

# Database shell
docker exec -it dna_toolkit-postgres-1 psql -U postgres -d genetic_health_db

# View logs
docker compose logs -f backend
docker compose logs -f frontend
```

## Database Schema

### Core Tables
- **users** — accounts with `is_admin`, `is_verified`
- **genetic_analyses** — analysis records with progress tracking (status, %, step, estimated_completion)

### Deduplication Architecture (key design decision)
- **genetic_markers** — global catalog of all variants (rsid, chr, pos, alleles). Never deleted.
- **analysis_variants** — links user analysis → marker + user's genotype. Cascade-deleted with analysis.
- **shared_variant_annotations** — external API results (ensembl_data, clinvar_data, pharmgkb_data (stores ClinPGx data), snpedia_data, litvar_data as JSON). Never deleted — accumulates as cache.
- **variant_annotations** — user-specific references to shared annotations.
- **variant_lookup_cache** — external lookup response cache with usage counting.

### Insight Tables (all cascade-delete on analysis)
health_risks, drug_responses, physical_traits, nutrition_traits, sports_performance, cognitive_profiles, personality_traits, ancestry_results, carrier_status, wellness_metrics, methylation_profiles, detoxification_profiles, rare_mutations, uncommon_mutations

### Config Tables
- **panel_marker_configs** — panel↔marker mappings (admin-managed)
- **variant_mappings** — replaces static registry (category, map_type, key, data JSON)
- **pending_discoveries** — auto-discovered markers awaiting admin approval

## Key Patterns & Conventions

### Backend
- **Auth**: All routes use `Depends(get_current_user)` except `/auth/login`, `/auth/register`, `/health`
- **Services**: Injected via `core/container.py` ServiceContainer (singletons + factories)
- **Rate Limiting**: Per-API in `api_endpoints.py` (NCBI: 10 req/s, ClinPGx: 2.0 req/s)
- **Analysis flow**: Upload → parse → store markers → background queue → external API calls → store results
- **Annotation data path**: `shared_variant_annotations.ensembl_data` → accessed via `annotation_data.get('annotations', {}).get('ensembl', {})`
- **Gene extraction**: `ensembl.data[0].transcript_consequences[0].gene_symbol`

### Frontend
- **Theme**: Always use centralized `utils/theme.ts` — import `getGlassBackground`, `getTextPrimary`, etc.
- **Panel pattern**: Each category panel receives `{ isDarkMode, data, token }` props, fetches its own data from `/api/analysis/dashboard-data`
- **Shared components**: Use `CategoryHeader`, `SectionCard`, `VariantLinks` from `categories/shared.tsx`
- **API calls**: Direct `fetch()` with `Bearer ${token}` header — no API client abstraction
- **UI library**: shadcn/ui (Radix primitives) + Tailwind CSS 4 + Framer Motion
- **Icons**: Lucide React (primary) + Tabler Icons
- **State**: React hooks + localStorage for theme/token persistence. No global state manager.

### Naming
- Keep file names simple — `analysis_service.py` not `comprehensive_analysis_service.py`
- Panel files match their category: `HealthPanel.tsx`, `SportsPanel.tsx`, etc.

## Common Pitfalls

- **pyenv issues**: The workspace has pyenv configured but Python 3.13 may not be installed. Use `/usr/bin/python3` or run inside Docker.
- **NCBI_API_KEY**: Must be set in environment or rate limits drop to 3 req/s.
- **Login field**: POST `/auth/login` uses `username` (not `email`).
- **Shared annotations persist**: They are never deleted even when users delete their data — this is by design for deduplication/caching.
- **JWT expiry**: 10 days — long for production but acceptable for development.
- **Frontend CORS**: Backend allows `localhost:3000` and `localhost:3001` only.