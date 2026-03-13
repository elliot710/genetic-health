"""
Pydantic schemas for API request/response models
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime

# User schemas
class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    password: Optional[str] = None

class User(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    is_admin: bool = False
    created_at: datetime
    
    class Config:
        from_attributes = True

# For API responses
class UserResponse(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    is_admin: bool = False
    created_at: datetime
    
    class Config:
        from_attributes = True

# Authentication schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

# Genetic analysis schemas
class GeneticAnalysisBase(BaseModel):
    filename: str
    file_type: str

class GeneticAnalysisCreate(GeneticAnalysisBase):
    analysis_results: Optional[Dict[str, Any]] = None

class GeneticAnalysis(GeneticAnalysisBase):
    id: int
    user_id: int
    analysis_results: Optional[Dict[str, Any]]
    upload_date: datetime
    
    class Config:
        from_attributes = True

# Variant schemas
class VariantBase(BaseModel):
    chromosome: str
    position: int
    rsid: Optional[str] = None
    ref_allele: str
    alt_allele: str
    genotype: Optional[str] = None

class VariantCreate(VariantBase):
    analysis_id: int
    quality: Optional[str] = None
    filter_status: Optional[str] = None
    info: Optional[Dict[str, Any]] = None

class Variant(VariantBase):
    id: int
    analysis_id: int
    quality: Optional[str]
    filter_status: Optional[str]
    info: Optional[Dict[str, Any]]
    
    class Config:
        from_attributes = True

# Health risk schemas
class HealthRiskCreate(BaseModel):
    analysis_id: int
    condition: str
    risk_level: str
    risk_score: Optional[str] = None
    associated_variants: Optional[List[str]] = None
    recommendations: Optional[List[str]] = None

class HealthRisk(HealthRiskCreate):
    id: int
    
    class Config:
        from_attributes = True

# Drug response schemas
class DrugResponseCreate(BaseModel):
    analysis_id: int
    gene: str
    drug: str
    response_type: Optional[str] = None
    recommendations: Optional[str] = None
    variants_involved: Optional[List[str]] = None

class DrugResponse(DrugResponseCreate):
    id: int
    
    class Config:
        from_attributes = True