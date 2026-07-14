# Genetic Health Analysis Toolkit

A full-stack genetic data analysis platform that provides personalised health insights from VCF and CSV genetic data. Upload raw genome files (23andMe, AncestryDNA, clinical VCF) and get a comprehensive dashboard across 13 health categories, powered by multi-source variant annotation.

**Live**: https://epigenic.xyz &nbsp;|&nbsp; **API docs**: https://api.epigenic.xyz/docs

---

## Features

- **Multi-format upload** — VCF and CSV files (23andMe, AncestryDNA, etc.)
- **13 analysis categories** — Health risks, drug responses, physical traits, nutrition, sports performance, cognitive profiles, personality, ancestry, carrier status, wellness, methylation, detoxification, rare/uncommon mutations
- **Multi-source annotation** — ClinVar, Ensembl VEP, ClinPGx, gnomAD, AlphaMissense, SNPedia, LitVar, AlphaFold, ChEMBL, FDA drug labels
- **Background analysis queue** — long-running jobs processed by a dedicated worker
- **Admin panel** — user management, variant registry, ETL imports, annotation backfill, discovery review
- **AI insights** — optional Gemini / OpenAI / Anthropic summaries per category
- **Google OAuth** — sign-in with Google in addition to username/password

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLAlchemy 2.0 (async), asyncpg, UV |
| Database | PostgreSQL 16 |
| Frontend | Next.js 15, TypeScript, Tailwind CSS 4, shadcn/ui, Framer Motion |
| Infrastructure | Docker Compose, Nginx, Alembic migrations |
| Observability | OpenTelemetry → Jaeger, Prometheus |

---

## Quick Start (Docker)

```bash
git clone git@github.com:elliot710/genetic-health.git dna_toolkit
cd dna_toolkit
cp .env.example .env          # fill in API keys
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

> **Note**: large local data sources (ClinVar, gnomAD, 1000G, VEP) need to be placed in `data_sources/` and imported via **Admin → Data** before analysis results will be fully populated.

---

## Project Structure

```
├── backend/
│   ├── main.py                 # FastAPI app, CORS, router mounts
│   ├── worker.py               # Background analysis worker
│   ├── api/                    # Route handlers (auth, upload, analysis, admin, …)
│   ├── services/               # Business logic (analysis, ETL, annotation, …)
│   ├── core/                   # Config, auth (JWT + bcrypt), DI container
│   └── db/                     # SQLAlchemy models, Pydantic schemas
├── frontend/src/
│   ├── app/                    # Next.js App Router entrypoint
│   └── components/
│       ├── Dashboard.tsx        # Main dashboard shell
│       ├── categories/          # 13 category panels + shared components
│       └── admin/AdminPanel.tsx # Admin panel
├── alembic/versions/           # Database migrations
├── data_sources/               # Local annotation files (not in git)
├── deploy.sh                   # Production deploy script
└── docker-compose.yml
```

---

## Development

### Local (without Docker)

```bash
# Backend
cd backend
PYTHONPATH=.. uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm run dev      # Turbopack
```

### Database migrations

```bash
# Apply all pending migrations
docker exec dna_toolkit-backend-1 uv run alembic upgrade head

# Create a new migration
docker exec dna_toolkit-backend-1 uv run alembic revision --autogenerate -m "description"
```

---

## Deployment

A `deploy.sh` script handles the full production deploy from your local machine:

```bash
./deploy.sh                   # pull + migrate + rebuild backend, worker, frontend
./deploy.sh --backend-only    # skip frontend rebuild (faster)
./deploy.sh --frontend-only   # UI changes only
./deploy.sh --no-build        # pull + migrate only
```

The script uses the server's `~/.ssh/github_deploy` deploy key, stashes any manual hotfixes, runs migrations, rebuilds Docker images, and waits for a healthy backend before exiting.

Unit Tests:
```bash
uv run pytest backend/tests/ --cov=backend --cov-report=term-missing -q --tb=no 2>&1 | tail -50

```

---

## API Overview

| Router | Prefix | Purpose |
|--------|--------|---------|
| auth | `/auth` | Register, login, OAuth, change-password |
| upload | `/upload` | VCF/CSV upload, delete data |
| analysis | `/api/analysis` | Start, status, results, dashboard-data |
| annotations | `/api/annotations` | Variant details, clinical summary, literature |
| variants | `/api/variants` | Cached multi-source lookup |
| admin | `/api/admin` | Users, registry, ETL, discoveries, jobs |
| insights | `/api/insights` | AI insight generation/status |

Full interactive docs at `/docs` (local) or https://api.epigenic.xyz/docs (production).

---

## Data Sources

Local files are placed in `data_sources/` and imported via the Admin ETL panel:

| Source | Import time | Tables populated |
|--------|------------|-----------------|
| ClinVar TSV + VCF | ~5 min | `clinvar_variants`, `clinvar_gene_conditions`, `clinvar_gene_stats` |
| gnomAD CADD TSV | ~10 min | `gnomad_variants` |
| 1000 Genomes VCF | ~15 min | `thousand_genomes_variants` |
| Ensembl VEP VCF | ~8 min | `ensembl_vep_annotations` |
| AlphaMissense TSV | instant | in-memory |

---

## Disclaimer

This toolkit is for educational and research purposes. Genetic information must be interpreted by qualified healthcare professionals. Do not use for medical diagnosis or treatment decisions.

## License

MIT — see [LICENSE](LICENSE).
