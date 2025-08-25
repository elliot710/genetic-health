"""
FAST OPTIMIZED genetic analysis job service - simplified for performance
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
from ..db.models import GeneticAnalysis, VariantAnnotation, GeneticVariant, HealthRisk, DrugResponse
from .genetic_api_service import GeneticAPIService
from .drug_response import DrugResponseAnalyzer
from .specialized_analyzers import SpecializedAnalyzerService

logger = logging.getLogger(__name__)

class GeneticAnalysisJob:
    """FAST optimized genetic analysis job with smart prioritization"""
    
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        self.api_service = GeneticAPIService()
        self.drug_analyzer = DrugResponseAnalyzer()
        self.specialized_analyzer = SpecializedAnalyzerService()
        self._job_start_time = None
        
    async def process_genetic_analysis(self, analysis_id: int, max_variants: Optional[int] = None):
        """Process genetic analysis with FAST optimizations for better performance"""
        self._job_start_time = datetime.utcnow()
        start_time = time.time()
        
        logger.info(f"🚀 FAST ANALYSIS STARTED for analysis_id {analysis_id} (user: {self.user_id})")
        
        try:
            async for session in get_session():
                # Load analysis efficiently
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
                
                # FAST OPTIMIZATION: Smart variant selection and limits
                variants_to_process = self._select_important_variants(variants, max_variants)
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
                        
                        # Fast annotation call
                        annotation_start = time.time()
                        annotation = await self.api_service.annotate_variant(str(variant.rsid))
                        api_calls_made += 1
                        annotation_time = time.time() - annotation_start
                        
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

    def _select_important_variants(self, variants: List, max_variants: Optional[int]) -> List:
        """FAST: Select most important variants for processing"""
        if max_variants is None:
            # When no limit, still prioritize for better user experience
            max_variants = min(len(variants), 500)  # Reasonable limit for speed
        
        # Prioritize variants by importance
        pharmacogenes = []
        pathogenic = []
        other_clinical = []
        common = []
        
        for variant in variants:
            rsid = str(variant.rsid).lower()
            clinical_sig = str(variant.clinical_significance or '').lower()
            
            # Top priority: Pharmacogenes (drug response)
            if any(gene in rsid for gene in ['cyp', 'adh', 'aldh', 'comt', 'mthfr', 'apoe']):
                pharmacogenes.append(variant)
            # High priority: Disease variants
            elif 'pathogenic' in clinical_sig and 'likely' not in clinical_sig:
                pathogenic.append(variant)
            # Medium priority: Other clinical variants
            elif clinical_sig and clinical_sig not in ['uncertain significance', 'benign', 'likely benign']:
                other_clinical.append(variant)
            else:
                common.append(variant)
        
        # Smart allocation of processing budget
        selected = []
        remaining = max_variants
        
        # Always include ALL pharmacogenes (they're critical)
        selected.extend(pharmacogenes)
        remaining -= len(pharmacogenes)
        
        if remaining > 0:
            # Allocate 60% to pathogenic
            pathogenic_limit = min(len(pathogenic), int(remaining * 0.6))
            selected.extend(pathogenic[:pathogenic_limit])
            remaining -= pathogenic_limit
            
            # Allocate 30% to other clinical
            clinical_limit = min(len(other_clinical), int(remaining * 0.3))
            selected.extend(other_clinical[:clinical_limit])
            remaining -= clinical_limit
            
            # Allocate remaining to common variants
            selected.extend(common[:remaining])
        
        logger.info(f"🎯 Selected {len(selected)} important variants:")
        logger.info(f"  - Pharmacogenes: {len(pharmacogenes)}")
        logger.info(f"  - Pathogenic: {min(len(pathogenic), int(max_variants * 0.6))}")
        logger.info(f"  - Other clinical: {min(len(other_clinical), int(max_variants * 0.3))}")
        logger.info(f"  - Common: {len(selected) - len(pharmacogenes) - min(len(pathogenic), int(max_variants * 0.6)) - min(len(other_clinical), int(max_variants * 0.3))}")
        
        return selected

    def _is_pharmacogene_variant(self, variant) -> bool:
        """Check if variant is in a pharmacogene"""
        rsid = str(variant.rsid).lower()
        return any(gene in rsid for gene in ['cyp', 'adh', 'aldh', 'comt', 'mthfr', 'apoe'])

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
                annotation_data=annotation,
                api_call_number=api_call_number,
                created_at=datetime.utcnow()
            )
            session.add(variant_annotation)
            await session.commit()
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
                    processed_variants=processed_variants,
                    updated_at=datetime.utcnow()
                )
                
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