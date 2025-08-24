"""
Genetic Health Analysis Toolkit - FastAPI Backend
"""
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
from typing import Dict, Any, Optional
import uvicorn
from io import StringIO
from datetime import timedelta

# Database imports
from .database import get_session, init_db
from .models import User
from .schemas import UserCreate, UserLogin, Token, User as UserSchema
from .user_service import UserService
from .auth import create_access_token, verify_token, ACCESS_TOKEN_EXPIRE_MINUTES

try:
    from .genetic_analyzer import GeneticAnalyzer
    from .vcf_parser import VCFParser
    from .health_insights import HealthInsights
    from .drug_response import DrugResponseAnalyzer
except ImportError:
    # For direct execution
    from genetic_analyzer import GeneticAnalyzer
    from vcf_parser import VCFParser
    from health_insights import HealthInsights
    from drug_response import DrugResponseAnalyzer

app = FastAPI(
    title="Genetic Health Analysis Toolkit",
    description="API for analyzing genetic data and providing health insights",
    version="1.0.0"
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    await init_db()

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize analyzers
genetic_analyzer = GeneticAnalyzer()
vcf_parser = VCFParser()
health_insights = HealthInsights()
drug_analyzer = DrugResponseAnalyzer()

@app.get("/")
async def root():
    return {"message": "Genetic Health Analysis Toolkit API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Authentication endpoints
@app.post("/auth/register", response_model=UserSchema)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_session)):
    """Register a new user"""
    user_service = UserService(db)
    
    # Check if user already exists
    existing_user = await user_service.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    existing_user = await user_service.get_user_by_username(user_data.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Create new user
    user = await user_service.create_user(user_data)
    return user

@app.post("/auth/login", response_model=Token)
async def login(form_data: UserLogin, db: AsyncSession = Depends(get_session)):
    """Login user and return access token"""
    user_service = UserService(db)
    
    user = await user_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Dependency for getting current user
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: AsyncSession = Depends(get_session)
) -> User:
    """Get current authenticated user"""
    token = credentials.credentials
    username = verify_token(token)
    
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_service = UserService(db)
    user = await user_service.get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

@app.get("/auth/me", response_model=UserSchema)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user

@app.post("/upload/vcf")
async def upload_vcf(file: UploadFile = File(...)):
    """Upload and parse VCF file"""
    if not file.filename or not file.filename.endswith('.vcf'):
        raise HTTPException(status_code=400, detail="File must be a VCF file")
    
    content = await file.read()
    variants = await vcf_parser.parse_vcf_content(content)
    
    return {
        "filename": file.filename,
        "variants_count": len(variants),
        "variants": variants[:100]  # Return first 100 variants
    }

@app.post("/upload/csv")
async def upload_csv(file: UploadFile = File(...)):
    """Upload and parse genetic CSV data"""
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV file")
    
    content = await file.read()
    df = pd.read_csv(StringIO(content.decode('utf-8')))
    
    # Analyze genetic data
    analysis = await genetic_analyzer.analyze_csv_data(df)
    
    return {
        "filename": file.filename,
        "rows": len(df),
        "columns": list(df.columns),
        "analysis": analysis
    }

@app.get("/analyze/health-insights/{rsid}")
async def get_health_insights(rsid: str):
    """Get health insights for a specific genetic variant"""
    insights = await health_insights.get_variant_insights(rsid)
    return insights

@app.get("/analyze/drug-response/{gene}")
async def get_drug_response(gene: str):
    """Get drug response information for a gene"""
    response = await drug_analyzer.get_drug_response(gene)
    return response

@app.post("/analyze/full-report")
async def generate_full_report(data: Dict[str, Any]):
    """Generate comprehensive health report"""
    # Combine all analyses
    vcf_data = data.get('vcf_variants', [])
    csv_data = data.get('csv_data', {})
    
    # Generate comprehensive report
    report = {
        "summary": await genetic_analyzer.generate_summary(vcf_data, csv_data),
        "health_risks": await health_insights.assess_health_risks(vcf_data),
        "drug_interactions": await drug_analyzer.assess_drug_interactions(vcf_data),
        "recommendations": await health_insights.generate_recommendations(vcf_data)
    }
    
    return report

@app.get("/variants/search")
async def search_variants(gene: Optional[str] = None, chromosome: Optional[str] = None, position: Optional[int] = None):
    """Search for genetic variants by gene, chromosome, or position"""
    results = await genetic_analyzer.search_variants(
        gene=gene,
        chromosome=chromosome,
        position=position
    )
    return results

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

def main():
    """Entry point for the genetic health toolkit"""
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)