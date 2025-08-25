"""
FAST OPTIMIZED genetic analysis job service - simplified for performance
"""
import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from ..db.database import get_session
from ..db.models import GeneticAnalysis, VariantAnnotation, DrugResponse
from .genetic_api_service import GeneticAPIService
from .drug_response import DrugResponseAnalyzer

logger = logging.getLogger(__name__)

class GeneticAnalysisJob:
    """FAST optimized genetic analysis job with smart prioritization"""
    
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        self.api_service = GeneticAPIService()
        self.drug_analyzer = DrugResponseAnalyzer()
        self._job_start_time = None
        
    async def process_genetic_analysis(self, analysis_id: int):
        """Process genetic analysis with FAST optimizations for better performance"""
        self._job_start_time = datetime.utcnow()
        start_time = time.time()
        
        logger.info(f"🚀 FAST ANALYSIS STARTED for analysis_id {analysis_id} (user: {self.user_id})")
        
        # Update status to show we've started
        await self._update_analysis_status(analysis_id, 'processing', 1, 'Loading analysis data', 0)
        
        try:
            async for session in get_session():
                # Load analysis efficiently
                logger.info(f"🔍 Loading analysis {analysis_id} for user {self.user_id}")
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
                
                logger.info(f"📊 Analysis found: {analysis.filename}, status: {analysis.analysis_status}")
                
                variants = analysis.variants
                logger.info(f"🧬 Found {len(variants) if variants else 0} variants in analysis")
                
                # Update total_variants count if it's not set correctly
                total_variants_count = len(variants) if variants else 0
                if total_variants_count > 0:
                    logger.info(f"🔧 Found {total_variants_count} variants, updating status")
                    await self._update_analysis_status(analysis_id, 'processing', 5, 'Loading variants', 0, total_variants_count)
                
                if not variants:
                    logger.warning(f"⚠️ No variants found for analysis {analysis_id}")
                    await self._update_analysis_status(analysis_id, 'completed', 100, 'No variants to process', 0)
                    return {"message": "No variants to process", "user_id": self.user_id}
                
                # PROCESS ALL VARIANTS: No filtering, process everything!
                variants_to_process = variants  # Process ALL variants
                total_to_process = len(variants_to_process)
                
                # FAST OPTIMIZATION: Determine API delay based on dataset size
                if total_to_process <= 20:
                    api_delay = 0.1    # Comprehensive for small datasets
                elif total_to_process <= 100:
                    api_delay = 0.05   # Balanced for medium datasets  
                else:
                    api_delay = 0.02   # Ultra-fast for large datasets
                
                logger.info(f"📊 FAST MODE: Processing {total_to_process} key variants with {api_delay}s delay")
                
                # Initialize tracking
                processed_count = 0
                api_calls_made = 0
                health_risks = []
                drug_responses = []
                
                # FAST PROCESSING: Simple sequential with optimized delays
                for i, variant in enumerate(variants_to_process):
                    try:
                        logger.info(f"🧬 Processing variant {i+1}/{total_to_process}: {variant.rsid}")
                        
                        # Check if already processed (skip duplicates)
                        if await self._variant_already_processed(session, variant, analysis_id):
                            processed_count += 1
                            logger.info(f"⏭️ Skipped {variant.rsid} - already processed")
                            continue
                        
                        # Fast annotation call with timing
                        start_time = time.time()
                        annotation = await self.api_service.annotate_variant(str(variant.rsid))
                        api_time = time.time() - start_time
                        api_calls_made += 1
                        
                        logger.info(f"⚡ Variant {variant.rsid} annotated in {api_time:.2f}s")
                        
                        if annotation:
                            # Save annotation data
                            await self._save_variant_annotation(session, variant, annotation, analysis_id, api_calls_made)
                            
                            # Generate essential insights only (for speed)
                            if self._is_pharmacogene_variant(variant):
                                drug_response = await self._generate_drug_response(variant, annotation)
                                if drug_response:
                                    drug_responses.append(drug_response)
                        
                        processed_count += 1
                        
                        # Update progress every 10 variants
                        if processed_count % 10 == 0:
                            progress = min(int(processed_count / total_to_process * 100), 99)
                            elapsed = time.time() - start_time
                            rate = processed_count / elapsed if elapsed > 0 else 0
                            eta = (total_to_process - processed_count) / rate if rate > 0 else 0
                            
                            logger.info(f"📊 Progress: {processed_count}/{total_to_process} ({progress}%) - "
                                      f"Rate: {rate:.1f}/sec, ETA: {eta:.0f}s")
                            
                            await self._update_analysis_status(
                                analysis_id, 'processing', progress,
                                f'Fast processing - {processed_count}/{total_to_process} variants',
                                processed_count
                            )
                        
                        # Optimized delay
                        await asyncio.sleep(api_delay)
                        
                    except Exception as e:
                        logger.error(f"❌ Error processing {variant.rsid}: {e}")
                        processed_count += 1
                        continue
                
                # Finalize analysis
                await self._finalize_analysis(session, analysis_id, health_risks, drug_responses)
                
                total_time = time.time() - start_time
                rate = processed_count / total_time if total_time > 0 else 0
                
                logger.info(f"🎉 FAST ANALYSIS COMPLETED in {total_time:.1f}s")
                logger.info(f"📊 Processed {processed_count} variants at {rate:.1f} variants/sec")
                logger.info(f"🔥 Made {api_calls_made} API calls")
                
                return {
                    "status": "completed",
                    "user_id": self.user_id,
                    "processed_variants": processed_count,
                    "api_calls_made": api_calls_made,
                    "processing_time": total_time,
                    "processing_rate": rate
                }
                
        except Exception as e:
            analysis_duration = (datetime.utcnow() - self._job_start_time).total_seconds() if hasattr(self, '_job_start_time') else 0
            logger.error(f"💥 FAST ANALYSIS FAILED for analysis_id {analysis_id}: {str(e)}")
            
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

    def _is_pharmacogene_variant(self, variant) -> bool:
        """Check if variant is in a pharmacogene"""
        rsid = str(variant.rsid).lower()
        return any(gene in rsid for gene in ['cyp', 'adh', 'aldh', 'comt', 'mthfr', 'apoe'])

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
                
                # Generate essential insights only (for speed)
                drug_response = None
                if self._is_pharmacogene_variant(variant):
                    drug_response = await self._generate_drug_response(variant, annotation)
                    
                return {
                    'success': True,
                    'variant': variant,
                    'annotation': annotation,
                    'drug_response': drug_response,
                    'api_time': api_time
                }
            else:
                return {'success': False, 'variant': variant, 'error': 'No annotation'}
                
        except Exception as e:
            logger.error(f"❌ Error processing variant {variant.rsid}: {e}")
            return {'success': False, 'variant': variant, 'error': str(e)}

    async def _variant_already_processed(self, session: AsyncSession, variant, analysis_id: int) -> bool:
        """Check if variant already has annotation data"""
        try:
            query = select(VariantAnnotation).where(
                VariantAnnotation.variant_id == variant.id,
                VariantAnnotation.analysis_id == analysis_id
            )
            result = await session.execute(query)
            return result.scalar_one_or_none() is not None
        except Exception:
            return False

    async def _save_variant_annotation(self, session: AsyncSession, variant, annotation: Dict, 
                                     analysis_id: int, api_call_number: int):
        """Save variant annotation to database"""
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
            await session.rollback()

    async def _generate_drug_response(self, variant, annotation: Dict) -> Optional[Dict]:
        """Generate drug response analysis for pharmacogene variants"""
        try:
            # Simple drug response logic for speed
            if annotation and 'annotations' in annotation:
                return {
                    'variant_id': variant.id,
                    'drug_class': 'metabolizer_enzyme',
                    'response_type': 'metabolic_rate',
                    'confidence': 'medium',
                    'recommendation': 'Consult pharmacist for dosing guidance',
                    'created_at': datetime.utcnow()
                }
        except Exception as e:
            logger.error(f"❌ Failed to generate drug response for {variant.rsid}: {e}")
        return None

    async def _update_analysis_status(self, analysis_id: int, status: str, 
                                    progress: int, current_step: str, processed_variants: int = 0, total_variants: Optional[int] = None):
        """Update analysis progress in database"""
        try:
            async for session in get_session():
                update_query = update(GeneticAnalysis).where(
                    GeneticAnalysis.id == analysis_id
                )
                if self.user_id is not None:
                    update_query = update_query.where(GeneticAnalysis.user_id == self.user_id)
                
                update_values = {
                    'analysis_status': status,
                    'progress_percentage': progress,
                    'current_step': current_step,
                    'processed_variants': processed_variants
                }
                
                # Update total_variants if provided
                if total_variants is not None:
                    update_values['total_variants'] = total_variants
                
                update_query = update_query.values(**update_values)
                
                await session.execute(update_query)
                await session.commit()
        except Exception as e:
            logger.error(f"❌ Failed to update analysis status: {e}")

    async def _finalize_analysis(self, session: AsyncSession, analysis_id: int, 
                               health_risks: List, drug_responses: List):
        """Finalize analysis and save results"""
        try:
            # Save drug responses
            for drug_data in drug_responses:
                drug_response = DrugResponse(**drug_data, analysis_id=analysis_id)
                session.add(drug_response)
            
            await session.commit()
            
            # Final status update
            await self._update_analysis_status(
                analysis_id, 'completed', 100, 
                'Analysis completed successfully', 0
            )
            
            logger.info(f"✅ Analysis {analysis_id} finalized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to finalize analysis: {e}")
            await session.rollback()

    # Backward compatibility method
    async def process_analysis(self, analysis_id: int, max_variants: Optional[int] = None):
        """Alias for backward compatibility with existing API routes"""
        return await self.process_genetic_analysis(analysis_id)

# Alias for backward compatibility with existing imports
AnalysisJob = GeneticAnalysisJob