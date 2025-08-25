# Genetic Health Analysis Toolkit

A full-stack genetic data analysis platform providing personalized health insights from VCF and CSV genetic data.

## Architecture Overview

### Backend (FastAPI + UV)
- **Layered Architecture**: `api/` routes → `services/` business logic → `db/` data layer
- **API Structure**: Modular routers in `backend/api/` (auth, upload, analysis, annotation)
- **External APIs**: Centralized configuration in `services/api_endpoints.py` for NCBI, PharmGKB, Ensembl, LitVar
- **Authentication**: JWT-based with SQLAlchemy async sessions

### Frontend (Next.js 15 + TypeScript)
- **Glassmorphism UI**: Centralized theme system in `utils/theme.ts` with dark/light mode support
- **Category Components**: 10 specialized panels in `components/categories/` (Health, Ancestry, Sports, etc.)
- **State Management**: React hooks with localStorage persistence for theme preferences

### Database (PostgreSQL + SQLAlchemy)
- **Async ORM**: SQLAlchemy 2.0 with async sessions
- **Models**: User, GeneticAnalysis, GeneticVariant, HealthRisk, DrugResponse in `db/models.py`
- **Migrations**: Alembic configured for schema versioning

Everything is running in docker with hot reload.

## Development Workflow

### Essential Commands
```bash
# Backend (from root)
cd backend && PYTHONPATH=.. uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm run dev

# Database
alembic upgrade head  # Apply migrations
alembic revision --autogenerate -m "description"  # Create migration
```

### VS Code Tasks
- "Start Both Servers" - Concurrent backend/frontend development
- Available in Command Palette → "Tasks: Run Task"

## Key Patterns & Conventions

### Backend Service Layer
```python
# Service pattern example
class GeneticAPIService:
    async def annotate_variant(self, rsid: str) -> Dict[str, Any]:
        # Rate-limited external API calls
        # Error handling with retries
        # Response caching
```

### Frontend Theme System
```typescript
// Centralized theme utilities
import { getGlassBackground, getTextPrimary } from '../../utils/theme'

// Usage in components
const glassBackground = getGlassBackground(isDarkMode);
const textPrimary = getTextPrimary(isDarkMode);
```

### API Integration
- **Rate Limiting**: Configured per external API in `api_endpoints.py`
- **Authentication**: All routes protected with `Depends(get_current_user)`
- **Background Processing**: Async genetic analysis after file upload

## Critical Integration Points

### File Upload Flow
1. `upload_routes.py` → VCF parsing → Database storage
2. Background task triggers external API analysis
3. Results stored and available via analysis endpoints

### External API Services
- **NCBI E-utilities**: ClinVar, PubMed, dbSNP integration
- **PharmGKB**: Drug response and pharmacogenomic data
- **Ensembl**: Variant effect prediction and gene lookup

### Frontend Component Architecture
- **Dashboard**: `ModernDashboard.tsx` orchestrates all category panels
- **Panel Pattern**: Each category extends base glassmorphism theme
- **Data Flow**: Props drilling from dashboard to specialized panels

## Common Debugging

### Backend Issues
```bash
# Check database connection
uv run python -c "from backend.db.database import init_db; import asyncio; asyncio.run(init_db())"

# API rate limit errors - check `api_endpoints.py` configurations
# Auth issues - verify JWT token in request headers
```

### Frontend Build Errors
```bash
# Theme/styling issues
npm run build  # Check for TypeScript errors in category components

# Common: Unused imports in category panels after theme centralization
# Fix: Remove unused getThemeClass imports where centralized utilities are used
```

### Database Schema
```sql
-- Key tables for genetic analysis
SELECT * FROM genetic_analyses;  -- Analysis metadata
SELECT * FROM genetic_variants;  -- Individual variants
SELECT * FROM health_risks;      -- Risk assessments  
SELECT * FROM drug_responses;    -- Pharmacogenomic data
```

## URLs & Documentation
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000/docs (Swagger UI)
- **Database**: PostgreSQL on default port 5432

### User credentials

email: elliotalderson710@gmail.com
password: Victor123!