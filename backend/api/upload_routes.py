"""
File upload API routes with database storage and genetic analysis
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Dict, Any
import asyncio
from datetime import datetime

from ..db.database import get_session
from ..db.models import GeneticAnalysis, GeneticVariant, HealthRisk, DrugResponse
from ..utils.vcf_parser import VCFParser
from ..services.genetic_api_service import GeneticAPIService
from ..services.analysis_job import AnalysisJob
from .auth_routes import get_current_user

router = APIRouter(prefix="/upload", tags=["upload"])


async def process_genetic_analysis(analysis_id: Any):
    """Background task to analyze genetic variants using external APIs"""
    try:
        # Use the comprehensive analysis job service
        analysis_job = AnalysisJob()
        # Convert analysis_id to int if needed
        actual_id = analysis_id if isinstance(analysis_id, int) else int(analysis_id)
        # Remove max_variants limit to process ALL variants
        await analysis_job.process_analysis(actual_id, max_variants=None)
        
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
                'upload_timestamp': datetime.now().isoformat(),
                'file_size': len(content)
            }
        )
        
        db.add(analysis)
        await db.flush()  # Get the analysis ID
        await db.refresh(analysis)  # Refresh to get the actual ID value
        
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
        analysis_id = analysis.id
        asyncio.create_task(process_genetic_analysis(analysis_id))
        
        return {
            "analysis_id": analysis_id,
            "filename": file.filename,
            "variants": variants[:10],  # Return first 10 for preview
            "total_variants": len(variants),
            "stored_variants": len(db_variants),
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
    """Upload and parse CSV file with genetic data"""
    
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file"
        )
    
    try:
        import pandas as pd
        import io
        
        # Read CSV file
        content = await file.read()
        
        # Parse CSV with flexible approach
        try:
            # Try reading with pandas, skipping comment lines starting with #
            df = pd.read_csv(io.BytesIO(content), comment='#')
        except Exception:
            try:
                # Try tab-separated
                df = pd.read_csv(io.BytesIO(content), sep='\t', comment='#')
            except Exception:
                try:
                    # Try comma-separated, skipping bad lines
                    df = pd.read_csv(io.BytesIO(content), sep=',', on_bad_lines='skip', comment='#')
                except Exception:
                    # Last resort - try to manually skip comment lines
                    lines = content.decode('utf-8').split('\n')
                    data_lines = [line for line in lines if not line.startswith('#') and line.strip()]
                    if data_lines:
                        df = pd.read_csv(io.StringIO('\n'.join(data_lines)))
                    else:
                        raise ValueError("Unable to parse CSV file")
        
        # Clean the DataFrame
        df = df.dropna(how='all')
        
        # Create genetic analysis record
        analysis = GeneticAnalysis(
            user_id=current_user.id,
            filename=file.filename,
            file_type='csv',
            analysis_results={
                'total_rows': len(df),
                'columns': list(df.columns),
                'upload_timestamp': datetime.now().isoformat(),
                'file_size': len(content)
            }
        )
        
        db.add(analysis)
        await db.flush()
        await db.refresh(analysis)  # Refresh to get the actual ID value
        
        # If CSV contains genetic variant data, parse and save
        genetic_columns = ['chromosome', 'position', 'rsid', 'ref', 'alt', 'genotype']
        has_genetic_data = any(col.lower() in [c.lower() for c in df.columns] for col in genetic_columns)
        
        if has_genetic_data:
            db_variants = []
            for _, row in df.iterrows():  # Process all rows
                # Map common column names - handle both lowercase and uppercase variants
                chromosome = str(row.get('chromosome', row.get('chr', row.get('CHROM', row.get('CHROMOSOME', '')))))
                
                # Handle position more carefully
                position_value = row.get('position', row.get('pos', row.get('POS', row.get('POSITION', 0))))
                try:
                    position = int(position_value) if position_value and str(position_value).strip() != '' else 0
                except (ValueError, TypeError):
                    position = 0
                
                rsid = str(row.get('rsid', row.get('RS_ID', row.get('ID', row.get('RSID', '')))))
                ref = str(row.get('ref', row.get('reference', row.get('REF', ''))))
                alt = str(row.get('alt', row.get('alternate', row.get('ALT', ''))))
                # For MyHeritage format, RESULT contains the genotype
                genotype = str(row.get('genotype', row.get('GT', row.get('RESULT', ''))))
                
                if chromosome and chromosome.strip() and position > 0:
                    db_variant = GeneticVariant(
                        analysis_id=analysis.id,
                        chromosome=chromosome,
                        position=position,
                        rsid=rsid if rsid and rsid != 'nan' and rsid.strip() else None,
                        ref_allele=ref if ref and ref != 'nan' and ref.strip() else '',
                        alt_allele=alt if alt and alt != 'nan' and alt.strip() else '',
                        genotype=genotype if genotype and genotype != 'nan' and genotype.strip() else None,
                        info={'source': 'csv_upload'}
                    )
                    db_variants.append(db_variant)
            
            if db_variants:
                db.add_all(db_variants)
                await db.commit()
                
                # Start background analysis
                analysis_id = analysis.id
                asyncio.create_task(process_genetic_analysis(analysis_id))
                
                return {
                    "analysis_id": analysis_id,
                    "filename": file.filename,
                    "total_rows": len(df),
                    "genetic_variants_found": len(db_variants),
                    "columns": list(df.columns),
                    "preview": df.head(5).to_dict(orient='records'),
                    "status": "uploaded",
                    "message": "CSV file uploaded with genetic data. Analysis is being processed in the background."
                }
        
        await db.commit()
        
        return {
            "analysis_id": analysis.id,
            "filename": file.filename,
            "total_rows": len(df),
            "columns": list(df.columns),
            "preview": df.head(5).to_dict(orient='records'),
            "status": "uploaded",
            "message": f"CSV file uploaded successfully. Analysis record saved with ID {analysis.id}. No genetic variant data detected in columns: {list(df.columns)}"
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
) -> Dict[str, Any]:
    """Delete all uploaded genetic data for the current user"""
    
    try:
        user_id = current_user.id
        
        # Get all analyses for this user
        analyses_result = await db.execute(
            select(GeneticAnalysis).where(GeneticAnalysis.user_id == user_id)
        )
        analyses = analyses_result.scalars().all()
        
        deleted_count = 0
        for analysis in analyses:
            # Delete variants
            await db.execute(
                delete(GeneticVariant).where(GeneticVariant.analysis_id == analysis.id)
            )
            
            # Delete health risks
            await db.execute(
                delete(HealthRisk).where(HealthRisk.analysis_id == analysis.id)
            )
            
            # Delete drug responses
            await db.execute(
                delete(DrugResponse).where(DrugResponse.analysis_id == analysis.id)
            )
            
            # Delete the analysis itself
            await db.delete(analysis)
            deleted_count += 1
        
        await db.commit()
        
        return {
            "message": f"Successfully deleted {deleted_count} analyses and all associated data for user {current_user.username}",
            "status": "success",
            "deleted_analyses": deleted_count
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
        user_id = current_user.id
        
        # Get all analyses for this user
        analyses_result = await db.execute(
            select(GeneticAnalysis).where(GeneticAnalysis.user_id == user_id)
        )
        analyses = analyses_result.scalars().all()
        
        # Count variants
        total_variants = 0
        for analysis in analyses:
            variants_result = await db.execute(
                select(GeneticVariant).where(GeneticVariant.analysis_id == analysis.id)
            )
            variants_count = len(variants_result.scalars().all())
            total_variants += variants_count
        
        # Get health risks count
        health_risks_result = await db.execute(
            select(HealthRisk).where(HealthRisk.analysis_id.in_([a.id for a in analyses]))
        )
        health_risks_count = len(health_risks_result.scalars().all())
        
        # Get drug responses count
        drug_responses_result = await db.execute(
            select(DrugResponse).where(DrugResponse.analysis_id.in_([a.id for a in analyses]))
        )
        drug_responses_count = len(drug_responses_result.scalars().all())
        
        return {
            "user_id": user_id,
            "username": current_user.username,
            "data_summary": {
                "uploaded_files": len(analyses),
                "total_variants": total_variants,
                "health_risks_identified": health_risks_count,
                "drug_responses_analyzed": drug_responses_count,
                "last_upload": analyses[-1].upload_date.isoformat() if analyses else None,
                "file_types": list(set([a.file_type for a in analyses]))
            },
            "analyses": [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "file_type": a.file_type,
                    "upload_date": a.upload_date.isoformat(),
                    "total_variants": a.analysis_results.get('total_variants', 0)
                }
                for a in analyses
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get data summary: {str(e)}"
        )


@router.get("/analysis/{analysis_id}")
async def get_analysis_results(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get detailed results for a specific analysis"""
    
    try:
        # Get the analysis
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        # Get health risks
        health_risks_result = await db.execute(
            select(HealthRisk).where(HealthRisk.analysis_id == analysis_id)
        )
        health_risks = health_risks_result.scalars().all()
        
        # Get drug responses
        drug_responses_result = await db.execute(
            select(DrugResponse).where(DrugResponse.analysis_id == analysis_id)
        )
        drug_responses = drug_responses_result.scalars().all()
        
        # Get sample variants
        variants_result = await db.execute(
            select(GeneticVariant).where(GeneticVariant.analysis_id == analysis_id).limit(20)
        )
        variants = variants_result.scalars().all()
        
        return {
            "analysis": {
                "id": analysis.id,
                "filename": analysis.filename,
                "file_type": analysis.file_type,
                "upload_date": analysis.upload_date.isoformat(),
                "results": analysis.analysis_results
            },
            "health_risks": [
                {
                    "condition": hr.condition,
                    "risk_level": hr.risk_level,
                    "risk_score": hr.risk_score,
                    "associated_variants": hr.associated_variants,
                    "recommendations": hr.recommendations
                }
                for hr in health_risks
            ],
            "drug_responses": [
                {
                    "gene": dr.gene,
                    "drug": dr.drug,
                    "response_type": dr.response_type,
                    "recommendations": dr.recommendations,
                    "variants_involved": dr.variants_involved
                }
                for dr in drug_responses
            ],
            "sample_variants": [
                {
                    "chromosome": v.chromosome,
                    "position": v.position,
                    "rsid": v.rsid,
                    "ref_allele": v.ref_allele,
                    "alt_allele": v.alt_allele,
                    "genotype": v.genotype
                }
                for v in variants
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analysis results: {str(e)}"
        )


@router.post("/trigger-analysis/{analysis_id}")
async def trigger_manual_analysis(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, str]:
    """Manually trigger background genetic analysis for an existing upload"""
    
    try:
        # Verify the analysis belongs to the current user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        # Trigger background analysis with a new database session
        async def trigger_analysis():
            await process_genetic_analysis(analysis_id)
        
        asyncio.create_task(trigger_analysis())
        
        return {
            "message": f"Background genetic analysis triggered for analysis {analysis_id}",
            "status": "processing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger analysis: {str(e)}"
        )


@router.post("/search-variant")
async def search_variant(
    data: Dict[str, str],
    current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    """Search for variant information using external APIs"""
    
    variant_id = data.get("variant_id", "").strip()
    if not variant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Variant ID is required"
        )
    
    try:
        async with GeneticAPIService() as api_service:
            # Get variant information from Ensembl
            ensembl_result = await api_service.get_variant_info_from_ensembl(variant_id)
            
            # Get PharmGKB information
            pharmgkb_result = await api_service.get_pharmgkb_variant_info(variant_id)
            
            # Combine results
            combined_result = {
                "rsid": variant_id,
                "ensembl": ensembl_result,
                "pharmgkb": pharmgkb_result,
                "search_timestamp": datetime.now().isoformat()
            }
            
            # Extract key information for display
            display_result = {
                "rsid": variant_id,
                "source": "Multiple databases",
                "name": ensembl_result.get("name") if ensembl_result and not ensembl_result.get("error") else None,
                "most_severe_consequence": ensembl_result.get("most_severe_consequence") if ensembl_result and not ensembl_result.get("error") else None,
                "clinical_significance": ensembl_result.get("clinical_significance", []) if ensembl_result and not ensembl_result.get("error") else [],
                "minor_allele": ensembl_result.get("minor_allele") if ensembl_result and not ensembl_result.get("error") else None,
                "minor_allele_freq": ensembl_result.get("minor_allele_freq") if ensembl_result and not ensembl_result.get("error") else None,
                "pharmgkb_found": pharmgkb_result.get("found", False) if pharmgkb_result else False,
                "raw_data": combined_result
            }
            
            return display_result
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search variant: {str(e)}"
        )