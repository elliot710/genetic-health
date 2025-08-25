"""
Optimized genetic analysis job service with performance improvements.
"""
import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from ..db.database import get_session
from ..db.models import GeneticAnalysis, VariantAnnotation, HealthRisk, DrugResponse
from .genetic_api_service import GeneticAPIService
from .health_insights import HealthInsights
from .drug_response import DrugResponseAnalyzer
from .specialized_analyzers import SpecializedAnalyzerService

logger = logging.getLogger(__name__)

class OptimizedAnalysisJob:
    """Enhanced genetic analysis job with performance optimizations"""
    
    def __init__(self, db_session, user_id=None):
        self.db_session = db_session
        self.user_id = user_id
        self.api_service = GeneticAPIService()
        self.health_insights = HealthInsights()
        self.drug_response_analyzer = DrugResponseAnalyzer()
        self.specialized_analyzer = SpecializedAnalyzerService()
        self._job_start_time = None
        
    async def process_genetic_analysis(self, analysis_id: int):
        """Process ALL genetic variants without filtering - simplified approach"""
        self._job_start_time = datetime.utcnow()
        start_time = time.time()
        
        logger.info(f"🚀 PROCESSING ALL VARIANTS for analysis_id {analysis_id} (user: {self.user_id})")
        
        try:
            async for session in get_session():
                # Load analysis and variants efficiently
                analysis_query = select(GeneticAnalysis).options(
                    selectinload(GeneticAnalysis.variants)
                ).where(GeneticAnalysis.id == analysis_id)
                
                if self.user_id is not None:
                    analysis_query = analysis_query.where(GeneticAnalysis.user_id == self.user_id)
                    
                result = await session.execute(analysis_query)
                analysis = result.scalar_one_or_none()
                
                if not analysis:
                    logger.error(f"❌ Analysis {analysis_id} not found for user {self.user_id}")
                    return {"error": "Analysis not found", "user_id": self.user_id}
                
                variants = analysis.variants
                if not variants:
                    logger.warning(f"⚠️ No variants found for analysis {analysis_id}")
                    await self._update_analysis_status(analysis_id, 'completed', 100, 'No variants to process', 0)
                    return {"message": "No variants to process", "user_id": self.user_id}
                
                # PROCESS ALL VARIANTS - no filtering!
                total_to_process = len(variants)
                logger.info(f"📊 Processing ALL {total_to_process} variants")
                
                # Initialize counters
                processed_count = 0
                api_calls_made = 0
                
                # Determine API delay based on dataset size for speed
                if total_to_process <= 20:
                    api_delay = 0.1    # Comprehensive for small datasets
                elif total_to_process <= 100:
                    api_delay = 0.05   # Balanced for medium datasets  
                else:
                    api_delay = 0.02   # Ultra-fast for large datasets
                
                logger.info(f"📊 FAST MODE: Processing {total_to_process} variants with {api_delay}s delay")
                
                # Process variants in batches for speed
                batch_size = 3  # Conservative batch size
                for i in range(0, len(variants), batch_size):
                    batch = variants[i:i + batch_size]
                    batch_start_time = time.time()
                    
                    # Process batch concurrently
                    batch_tasks = []
                    for variant in batch:
                        batch_tasks.append(self._process_single_variant(variant, analysis_id, session))
                    
                    # Wait for all variants in this batch to complete
                    if batch_tasks:
                        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                        
                        # Process results
                        for result in batch_results:
                            if isinstance(result, Exception):
                                logger.error(f"❌ Batch processing error: {result}")
                                continue
                                
                            if isinstance(result, dict) and result.get('success'):
                                processed_count += 1
                                api_calls_made += 1
                                logger.info(f"⚡ {result['variant'].rsid} processed in {result['api_time']:.2f}s")
                                
                        # Update progress
                        progress = min(95, int((processed_count / total_to_process) * 100))
                        batch_time = time.time() - batch_start_time
                        rate = len(batch_tasks) / batch_time if batch_time > 0 else 0
                        
                        logger.info(f"🚀 Batch {i//batch_size + 1}: {len(batch_tasks)} variants in {batch_time:.2f}s ({rate:.1f}/sec)")
                        
                        await self._update_analysis_status(
                            analysis_id, 'processing', progress, 
                            f"Processing all variants - {processed_count}/{total_to_process}", 
                            processed_count
                        )
                    
                    # Minimal delay between batches
                    await asyncio.sleep(api_delay)
                
                # Final completion - with comprehensive analysis
                logger.info(f"🧬 Generating comprehensive health insights...")
                health_results = await self._generate_health_insights(analysis_id)
                
                logger.info(f"💊 Analyzing drug responses...")
                drug_results = await self._generate_drug_responses(analysis_id)
                
                logger.info(f"🔬 Running specialized analysis...")
                specialized_results = await self._run_specialized_analysis(analysis_id)
                
                await self._update_analysis_status(
                    analysis_id, 'completed', 100, 
                    f'Completed - {processed_count}/{total_to_process} variants processed', 
                    processed_count
                )
                
                total_time = time.time() - start_time
                logger.info(f"🎉 Analysis {analysis_id} completed in {total_time:.2f}s")
                logger.info(f"📊 Processed {processed_count}/{total_to_process} variants with {api_calls_made} API calls")
                
                return {
                    "status": "completed",
                    "user_id": self.user_id,
                    "processed_variants": processed_count,
                    "total_variants": total_to_process,
                    "api_calls_made": api_calls_made,
                    "processing_time": total_time
                }
                
        except Exception as e:
            analysis_duration = (datetime.utcnow() - self._job_start_time).total_seconds() if hasattr(self, '_job_start_time') else 0
            logger.error(f"💥 ANALYSIS FAILED for analysis_id {analysis_id}: {str(e)}")
            
            try:
                await self._update_analysis_status(
                    analysis_id, 'failed', 0, 
                    f'Analysis failed: {type(e).__name__}', 0
                )
            except Exception as status_error:
                logger.error(f"❌ Failed to update analysis status: {status_error}")
            
            return {
                "error": f"Analysis job failed: {str(e)}", 
                "user_id": self.user_id,
                "duration_seconds": analysis_duration
            }
        finally:
            try:
                await self.api_service.close()
            except Exception:
                pass

    async def _process_single_variant(self, variant, analysis_id: int, session: AsyncSession) -> Dict:
        """Process a single variant asynchronously"""
        try:
            # Fast annotation call with timing
            start_time = time.time()
            annotation = await self.api_service.annotate_variant(str(variant.rsid))
            api_time = time.time() - start_time
            
            if annotation:
                # Save annotation data
                await self._save_variant_annotation(session, variant, annotation, analysis_id, 1)
                    
                return {
                    'success': True,
                    'variant': variant,
                    'annotation': annotation,
                    'api_time': api_time
                }
            else:
                return {'success': False, 'variant': variant, 'error': 'No annotation'}
                
        except Exception as e:
            logger.error(f"❌ Error processing variant {variant.rsid}: {e}")
            return {'success': False, 'variant': variant, 'error': str(e)}

    async def _save_variant_annotation(self, session: AsyncSession, variant, annotation: Dict, 
                                     analysis_id: int, api_call_number: int):
        """Save variant annotation data to database"""
        try:
            variant_annotation = VariantAnnotation(
                variant_id=variant.id,
                analysis_id=analysis_id,
                rsid=variant.rsid or f"chr{variant.chromosome}:{variant.position}",
                ensembl_data=annotation.get('ensembl', {}),
                clinvar_data=annotation.get('clinvar', {}),
                pharmgkb_data=annotation.get('pharmgkb', {}),
                api_calls_made=api_call_number
            )
            session.add(variant_annotation)
            # Don't commit here - let the main process handle commits
        except Exception as e:
            logger.error(f"❌ Failed to save annotation for variant {variant.id}: {e}")
    
    async def _update_analysis_status(self, analysis_id: int, status: str, 
                                    progress: int, current_step: str, processed_variants: int = 0):
        """Update analysis progress in database"""
        try:
            async for session in get_session():
                update_query = update(GeneticAnalysis).where(
                    GeneticAnalysis.id == analysis_id
                )
                if self.user_id is not None:
                    update_query = update_query.where(GeneticAnalysis.user_id == self.user_id)
                
                update_query = update_query.values(
                    analysis_status=status,
                    progress_percentage=progress,
                    current_step=current_step,
                    processed_variants=processed_variants
                )
                
                await session.execute(update_query)
                await session.commit()
        except Exception as e:
            logger.error(f"❌ Failed to update analysis status: {e}")

    async def _generate_health_insights(self, analysis_id: int) -> Dict:
        """Generate health insights for analyzed variants"""
        try:
            # Get all variants for this analysis
            query = select(VariantAnnotation).where(VariantAnnotation.analysis_id == analysis_id)
            result = await self.db_session.execute(query)
            variants = result.scalars().all()
            
            # Convert to list format for health insights
            variant_list = []
            for variant in variants:
                variant_list.append({
                    'rsid': variant.rsid,
                    'annotation_data': variant.annotation_data or {}
                })
            
            # Run health risk assessment
            health_results = await self.health_insights.assess_health_risks(variant_list)
            
            # Store health risks in database if we have results
            risks_created = 0
            if health_results.get('high_risk_variants'):
                for risk_variant in health_results['high_risk_variants']:
                    db_risk = HealthRisk(
                        analysis_id=analysis_id,
                        variant_id=risk_variant.get('rsid'),
                        condition=risk_variant.get('condition', 'Unknown'),
                        risk_level='high',
                        confidence=risk_variant.get('confidence', 0.0),
                        description=risk_variant.get('description', '')
                    )
                    self.db_session.add(db_risk)
                    risks_created += 1
            
            await self.db_session.commit()
            logger.info(f"Generated {risks_created} health insights")
            return {"health_risks_generated": risks_created}
            
        except Exception as e:
            logger.error(f"Failed to generate health insights: {e}")
            await self.db_session.rollback()
            return {"error": str(e)}

    async def _generate_drug_responses(self, analysis_id: int) -> Dict:
        """Generate drug response analysis for analyzed variants"""
        try:
            # Get all variants for this analysis
            query = select(VariantAnnotation).where(VariantAnnotation.analysis_id == analysis_id)
            result = await self.db_session.execute(query)
            variants = result.scalars().all()
            
            # Convert to list format for drug response analysis
            variant_list = []
            for variant in variants:
                variant_list.append({
                    'rsid': variant.rsid,
                    'annotation_data': variant.annotation_data or {}
                })
            
            # Run drug interaction assessment
            drug_results = await self.drug_response_analyzer.assess_drug_interactions(variant_list)
            
            # Store drug responses in database if we have results
            responses_created = 0
            if drug_results.get('interactions'):
                for interaction in drug_results['interactions']:
                    db_response = DrugResponse(
                        analysis_id=analysis_id,
                        variant_id=interaction.get('variant'),
                        drug_name=interaction.get('drug', 'Unknown'),
                        response_type=interaction.get('type', 'unknown'),
                        efficacy=interaction.get('efficacy', 'unknown'),
                        dosage_recommendation=interaction.get('dosage_rec', ''),
                        warnings=interaction.get('warnings', [])
                    )
                    self.db_session.add(db_response)
                    responses_created += 1
            
            await self.db_session.commit()
            logger.info(f"Generated {responses_created} drug responses")
            return {"drug_responses_generated": responses_created}
            
        except Exception as e:
            logger.error(f"Failed to generate drug responses: {e}")
            await self.db_session.rollback()
            return {"error": str(e)}

    async def _run_specialized_analysis(self, analysis_id: int) -> Dict:
        """Run specialized analysis including methylation, detox, etc."""
        try:
            # Get all variants for this analysis
            query = select(VariantAnnotation).where(VariantAnnotation.analysis_id == analysis_id)
            result = await self.db_session.execute(query)
            variants = result.scalars().all()
            
            specialized_results = 0
            
            # Process each variant through specialized analyzers
            for variant in variants:
                if variant.annotation_data:
                    # Use generate_all_specialized_profiles method
                    results = await self.specialized_analyzer.generate_all_specialized_profiles(
                        variant, variant.annotation_data, analysis_id, self.db_session
                    )
                    if results:
                        specialized_results += 1
            
            await self.db_session.commit()
            logger.info(f"Completed specialized analysis with {specialized_results} results")
            return {"specialized_analysis_completed": specialized_results}
            
        except Exception as e:
            logger.error(f"Failed to run specialized analysis: {e}")
            await self.db_session.rollback()
            return {"error": str(e)}

# Alias for compatibility
AnalysisJob = OptimizedAnalysisJob