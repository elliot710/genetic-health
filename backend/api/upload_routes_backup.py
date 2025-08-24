"""
File upload API routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from        analysis_results={
            'total_variants': len(variants),
            'upload_timestamp': datetime.now().isoformat(),
            'file_size': len(content)
        }lchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from sqlalchemy.sql import func
from typing import Dict, Any
import asyncio
from datetime import datetime

from ..db.database import get_session
from ..db.models import GeneticAnalysis, GeneticVariant, HealthRisk, DrugResponse
from ..utils.vcf_parser import VCFParser
from ..services.genetic_api_service import GeneticAPIService
from .auth_routes import get_current_user

router = APIRouter(prefix="/upload", tags=["upload"])

async def process_genetic_analysis(analysis_id: int, db: AsyncSession):
    """Background task to analyze genetic variants using external APIs"""
    try:
        async with GeneticAPIService() as api_service:
            # Get the analysis and its variants
            result = await db.execute(
                select(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
            )
            analysis = result.scalar_one_or_none()
            
            if not analysis:
                return
            
            # Get variants for this analysis
            variants_result = await db.execute(
                select(GeneticVariant).where(GeneticVariant.analysis_id == analysis_id)
            )
            variants = variants_result.scalars().all()
            
            # Process up to 20 variants to avoid overwhelming APIs
            sample_variants = variants[:20] if len(variants) > 20 else variants
            
            health_risks = []
            drug_responses = []
            
            for variant in sample_variants:
                if variant.rsid is not None:
                    # Get variant information from multiple sources
                    ensembl_info = await api_service.get_variant_info_from_ensembl(str(variant.rsid))
                    pharmgkb_info = await api_service.get_pharmgkb_variant_info(str(variant.rsid))
                    
                    # Process health risks from Ensembl
                    if 'clinical_significance' in ensembl_info:
                        for sig in ensembl_info['clinical_significance']:
                            if sig and sig.lower() in ['pathogenic', 'likely pathogenic', 'risk factor']:
                                health_risk = HealthRisk(
                                    analysis_id=analysis_id,
                                    condition=f"Variant {variant.rsid} associated condition",
                                    risk_level='moderate' if 'likely' in sig.lower() else 'high',
                                    risk_score=sig,
                                    associated_variants=[str(variant.rsid)],
                                    recommendations=["Consult with healthcare provider", "Consider genetic counseling"]
                                )
                                health_risks.append(health_risk)
                    
                    # Process drug responses from PharmGKB
                    if 'pharmacogenomics' in pharmgkb_info:
                        for drug_info in pharmgkb_info.get('pharmacogenomics', []):
                            drug_response = DrugResponse(
                                analysis_id=analysis_id,
                                gene=drug_info.get('gene', 'Unknown'),
                                drug=drug_info.get('drug', 'Unknown'),
                                response_type=drug_info.get('response', 'normal'),
                                recommendations=drug_info.get('recommendation', 'Standard dosing'),
                                variants_involved=[str(variant.rsid)]
                            )
                            drug_responses.append(drug_response)
            
            # Save health risks and drug responses
            if health_risks:
                db.add_all(health_risks)
            if drug_responses:
                db.add_all(drug_responses)
            
            await db.commit()
            
    except Exception as e:
        print(f"Error in background analysis: {str(e)}")

@router.post("/vcf")
async def upload_vcf(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Upload and parse VCF file, save to database, and analyze with APIs"""
    
    if not file.filename or not file.filename.endswith('.vcf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a VCF file"
        )
    
    try:
        # Read file content
        content = await file.read()
        
        # Parse VCF file
        parser = VCFParser()
        variants = await parser.parse_vcf_content(content)
        
        # Create genetic analysis record
        analysis = GeneticAnalysis(
            user_id=current_user.id,
            filename=file.filename,
            file_type='vcf',
            analysis_results={
                'total_variants': len(variants),
                'upload_timestamp': str(func.now()),
                'file_size': len(content)
            }
        )
        
        db.add(analysis)
        await db.flush()  # Get the analysis ID
        
        # Save variants to database
        db_variants = []
        for variant in variants:
            db_variant = GeneticVariant(
                analysis_id=analysis.id,
                chromosome=variant.get('chromosome', ''),
                position=variant.get('position', 0),
                rsid=variant.get('rsid'),
                ref_allele=variant.get('ref', ''),
                alt_allele=variant.get('alt', ''),
                genotype=variant.get('genotype'),
                quality=variant.get('quality'),
                filter_status=variant.get('filter'),
                info=variant.get('info', {})
            )
            db_variants.append(db_variant)
        
        db.add_all(db_variants)
        await db.commit()
        
        # Start background analysis with APIs
        asyncio.create_task(process_genetic_analysis(analysis.id, db))
        
        return {
            "analysis_id": analysis.id,
            "filename": file.filename,
            "variants": variants[:10],  # Return first 10 for preview
            "total_variants": len(variants),
            "status": "uploaded",
            "message": "File uploaded successfully. Genetic analysis is being processed in the background."
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process VCF file: {str(e)}"
        )

@router.post("/csv")
async def upload_csv(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Upload and parse CSV file"""
    
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file"
        )
    
    try:
        import pandas as pd
        import io
        
        # Read CSV file with error handling for inconsistent formats
        content = await file.read()
        
        # Try different parsing strategies for genetic data files
        try:
            # First try: Standard CSV parsing, skipping comment lines
            df = pd.read_csv(io.BytesIO(content), comment='#')
        except pd.errors.ParserError:
            # Second try: Skip bad lines and use flexible parsing
            try:
                df = pd.read_csv(
                    io.BytesIO(content), 
                    comment='#',
                    on_bad_lines='skip',
                    skip_blank_lines=True
                )
            except Exception:
                # Third try: Tab-separated files (common in genetic data)
                try:
                    df = pd.read_csv(
                        io.BytesIO(content), 
                        sep='\t',
                        comment='#',
                        on_bad_lines='skip',
                        skip_blank_lines=True
                    )
                except Exception:
                    # Fourth try: Manual parsing for complex genetic file formats
                    content_str = content.decode('utf-8')
                    lines = [line.strip() for line in content_str.split('\n') if line.strip()]
                    
                    # Filter out comment lines and empty lines
                    data_lines = [line for line in lines if not line.startswith('#') and line.strip()]
                    
                    if len(data_lines) > 0:
                        # Detect delimiter
                        first_line = data_lines[0]
                        if '\t' in first_line:
                            delimiter = '\t'
                        elif ',' in first_line:
                            delimiter = ','
                        elif ' ' in first_line:
                            delimiter = r'\s+'  # Multiple spaces
                        else:
                            delimiter = ','
                        
                        # Create DataFrame from cleaned data
                        df = pd.read_csv(
                            io.StringIO('\n'.join(data_lines)), 
                            sep=delimiter,
                            on_bad_lines='skip'
                        )
                    else:
                        raise ValueError("No valid data lines found in file")
        
        # Clean the DataFrame
        df = df.dropna(how='all')  # Remove completely empty rows
        
        # Convert to dictionary with error handling
        if len(df) == 0:
            analysis = {"message": "No valid data found in file", "rows": []}
            total_rows = 0
            columns = []
        else:
            # Limit the output size to prevent memory issues
            original_length = len(df)
            if original_length > 10000:
                df = df.head(10000)
                analysis = {
                    "message": f"Large file detected. Showing first 10,000 rows out of {original_length} total.",
                    "data": df.to_dict(orient='records')
                }
            else:
                analysis = df.to_dict(orient='records')
            
            total_rows = original_length
            columns = list(df.columns)
        
        return {
            "filename": file.filename,
            "analysis": analysis,
            "total_rows": total_rows,
            "columns": columns,
            "file_format": "CSV with flexible parsing"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process CSV file: {str(e)}"
        )

@router.delete("/data")
async def delete_user_data(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, str]:
    """Delete all uploaded genetic data for the current user"""
    
    try:
        # For now, we don't store the actual data in the database
        # This would be where we'd delete stored analysis results, uploaded files, etc.
        # In a real implementation, you might have:
        # - File storage deletion (S3, local files)
        # - Database cleanup for analysis results
        # - Cache invalidation
        
        # Simulate data deletion
        # user_id = current_user.id
        
        # Here you would implement actual data deletion:
        # await db.execute(delete(AnalysisResults).where(AnalysisResults.user_id == user_id))
        # await db.execute(delete(UploadedFiles).where(UploadedFiles.user_id == user_id))
        # await db.commit()
        
        return {
            "message": f"All genetic data for user {current_user.username} has been successfully deleted",
            "status": "success"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user data: {str(e)}"
        )

@router.get("/data-summary")
async def get_user_data_summary(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get summary of user's uploaded data"""
    
    try:
        # In a real implementation, this would query actual stored data
        # For now, return a mock summary
        
        return {
            "user_id": current_user.id,
            "username": current_user.username,
            "data_summary": {
                "uploaded_files": 0,  # Would be actual count from database
                "analysis_results": 0,  # Would be actual count from database
                "last_upload": None,  # Would be actual timestamp
                "total_variants": 0,  # Would be actual count
                "data_sources": []  # Would be actual list
            },
            "storage_usage": {
                "files_size_mb": 0,
                "analysis_size_mb": 0,
                "total_size_mb": 0
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get data summary: {str(e)}"
        )