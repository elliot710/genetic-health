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
from ..db.models import GeneticAnalysis, VariantAnnotation, Variant, HealthRisk, DrugResponse
from .genetic_api_service import GeneticAPIService
from .health_insights import HealthInsightGenerator
from .drug_response import DrugResponseAnalyzer
from .specialized_analyzers import SpecializedAnalyzer

logger = logging.getLogger(__name__)

class OptimizedAnalysisJob:
    """Enhanced genetic analysis job with performance optimizations"""
    
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        self.api_service = GeneticAPIService()
        self.health_generator = HealthInsightGenerator()
        self.drug_analyzer = DrugResponseAnalyzer()
        self.specialized_analyzer = SpecializedAnalyzer()
        self._job_start_time = None
        
    async def process_genetic_analysis(self, analysis_id: int, max_variants: Optional[int] = None):
        """Process genetic analysis with smart prioritization and performance optimizations"""
        self._job_start_time = datetime.utcnow()
        start_time = time.time()
        
        logger.info(f"🚀 OPTIMIZED ANALYSIS STARTED for analysis_id {analysis_id} (user: {self.user_id})")
        
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
                
                # OPTIMIZATION 1: Smart variant categorization and prioritization
                variant_groups = self._categorize_variants_optimized(variants)
                processing_plan = self._create_optimized_processing_plan(variant_groups, max_variants, len(variants))
                
                # OPTIMIZATION 2: Determine processing mode based on dataset size
                total_to_process = sum(len(group_variants) for group_variants in processing_plan.values())
                processing_mode = self._determine_processing_mode(total_to_process)
                
                logger.info(f"📊 Processing plan: {total_to_process} variants using {processing_mode} mode")
                for group_name, group_variants in processing_plan.items():
                    if group_variants:
                        logger.info(f"  - {group_name}: {len(group_variants)} variants")
                
                # Initialize counters
                processed_count = 0
                api_calls_made = 0
                health_risks = []
                drug_responses = []
                specialized_profiles_count = {
                    'cardiovascular': 0, 'neurological': 0, 'metabolic': 0,
                    'cancer': 0, 'immune': 0, 'rare_diseases': 0
                }
                
                # OPTIMIZATION 3: Process each group with appropriate strategy
                for group_name, group_variants in processing_plan.items():
                    if not group_variants:
                        continue
                        
                    logger.info(f"🧬 Processing {group_name}: {len(group_variants)} variants")
                    
                    if processing_mode == "fast":
                        # Fast mode: Essential annotations only
                        results = await self._process_group_fast(
                            session, group_variants, analysis_id, group_name, 
                            processed_count, total_to_process, start_time
                        )
                    else:
                        # Comprehensive mode: Full annotations
                        results = await self._process_group_comprehensive(
                            session, group_variants, analysis_id, group_name,
                            processed_count, total_to_process, start_time
                        )
                    
                    # Update counters
                    processed_count += results['processed']
                    api_calls_made += results['api_calls']
                    health_risks.extend(results.get('health_risks', []))
                    drug_responses.extend(results.get('drug_responses', []))
                    
                    for category, count in results.get('specialized_profiles', {}).items():
                        specialized_profiles_count[category] += count
                
                # Final analysis completion
                await self._finalize_analysis(
                    session, analysis_id, start_time, processed_count, api_calls_made,
                    health_risks, drug_responses, specialized_profiles_count
                )
                
                return {
                    "status": "completed",
                    "user_id": self.user_id,
                    "processed_variants": processed_count,
                    "api_calls_made": api_calls_made,
                    "processing_time": time.time() - start_time
                }
                
        except Exception as e:
            analysis_duration = (datetime.utcnow() - self._job_start_time).total_seconds() if hasattr(self, '_job_start_time') else 0
            logger.error(f"💥 OPTIMIZED ANALYSIS FAILED for analysis_id {analysis_id}: {str(e)}")
            
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

    def _categorize_variants_optimized(self, variants: List) -> Dict[str, List]:
        """Optimized variant categorization focusing on clinical importance"""
        groups = {
            'pharmacogenes': [],      # Highest priority - drug response
            'pathogenic': [],         # High priority - known disease variants  
            'likely_pathogenic': [],  # High priority - likely disease variants
            'common_clinvar': [],     # Medium priority - common clinical variants
            'other': []              # Lower priority - everything else
        }
        
        for variant in variants:
            # Enhanced categorization logic
            rsid = str(variant.rsid).lower()
            
            # Pharmacogenes - always highest priority
            if any(gene in rsid for gene in ['cyp', 'adh', 'aldh', 'comt', 'mthfr', 'apoe']):
                groups['pharmacogenes'].append(variant)
            # Pathogenic variants
            elif 'pathogenic' in str(variant.clinical_significance or '').lower():
                if 'likely' in str(variant.clinical_significance or '').lower():
                    groups['likely_pathogenic'].append(variant)
                else:
                    groups['pathogenic'].append(variant)
            # Common clinical variants
            elif variant.clinical_significance and variant.clinical_significance != 'Uncertain significance':
                groups['common_clinvar'].append(variant)
            else:
                groups['other'].append(variant)
        
        return groups
    
    def _create_optimized_processing_plan(self, variant_groups: Dict[str, List], 
                                        max_variants: Optional[int], total_variants: int) -> Dict[str, List]:
        """Create processing plan with smart limits for performance"""
        if max_variants is None:
            return variant_groups
        
        # Smart allocation based on clinical importance
        allocations = {}
        remaining_budget = max_variants
        
        # Priority 1: ALL pharmacogenes (they're critical)
        pharma_variants = variant_groups.get('pharmacogenes', [])
        allocations['pharmacogenes'] = pharma_variants
        remaining_budget -= len(pharma_variants)
        
        if remaining_budget > 0:
            # Priority 2: Pathogenic variants (60% of remaining)
            pathogenic_variants = variant_groups.get('pathogenic', [])
            pathogenic_limit = min(len(pathogenic_variants), int(remaining_budget * 0.6))
            allocations['pathogenic'] = pathogenic_variants[:pathogenic_limit]
            remaining_budget -= pathogenic_limit
            
            # Priority 3: Likely pathogenic (30% of remaining)
            likely_pathogenic_variants = variant_groups.get('likely_pathogenic', [])
            likely_limit = min(len(likely_pathogenic_variants), int(remaining_budget * 0.3))
            allocations['likely_pathogenic'] = likely_pathogenic_variants[:likely_limit]
            remaining_budget -= likely_limit
            
            # Priority 4: Common ClinVar variants (remaining budget)
            common_variants = variant_groups.get('common_clinvar', [])
            common_limit = min(len(common_variants), remaining_budget)
            allocations['common_clinvar'] = common_variants[:common_limit]
            
            # Skip 'other' variants when under budget constraints
            allocations['other'] = []
        
        return allocations
    
    def _determine_processing_mode(self, total_variants: int) -> str:
        """Determine optimal processing mode based on dataset size"""
        if total_variants <= 50:
            return "comprehensive"  # Full annotations
        elif total_variants <= 200:
            return "balanced"       # Selected annotations
        else:
            return "fast"          # Essential annotations only
    
    async def _process_group_fast(self, session: AsyncSession, variants: List, 
                                analysis_id: int, group_name: str, current_count: int,
                                total_count: int, start_time: float) -> Dict[str, Any]:
        """Fast processing mode - essential annotations only"""
        results = {
            'processed': 0,
            'api_calls': 0,
            'health_risks': [],
            'drug_responses': [],
            'specialized_profiles': {}
        }
        
        # Process in smaller batches for fast mode
        batch_size = 5
        api_delay = 0.05  # Minimal delay for speed
        
        for i in range(0, len(variants), batch_size):
            batch = variants[i:i + batch_size]
            
            for variant in batch:
                try:
                    # Fast annotation (basic Ensembl only)
                    annotation = await self.api_service.get_basic_annotation(str(variant.rsid))
                    results['api_calls'] += 1
                    
                    if annotation:
                        await self._save_variant_annotation(session, variant, annotation, analysis_id, results['api_calls'])
                        
                        # Generate only essential insights for speed
                        if group_name == 'pharmacogenes':
                            drug_response = await self.drug_analyzer.analyze_variant(variant, annotation)
                            if drug_response:
                                results['drug_responses'].append(drug_response)
                    
                    results['processed'] += 1
                    
                    # Progress update every batch
                    if results['processed'] % batch_size == 0:
                        progress = min(int((current_count + results['processed']) / total_count * 100), 99)
                        await self._update_analysis_status(
                            analysis_id, 'processing', progress,
                            f'Fast processing {group_name}', current_count + results['processed']
                        )
                    
                    await asyncio.sleep(api_delay)
                    
                except Exception as e:
                    logger.error(f"❌ Fast processing error for {variant.rsid}: {e}")
                    results['processed'] += 1
        
        return results
    
    async def _process_group_comprehensive(self, session: AsyncSession, variants: List,
                                         analysis_id: int, group_name: str, current_count: int,
                                         total_count: int, start_time: float) -> Dict[str, Any]:
        """Comprehensive processing mode - full annotations"""
        results = {
            'processed': 0,
            'api_calls': 0,
            'health_risks': [],
            'drug_responses': [],
            'specialized_profiles': {
                'cardiovascular': 0, 'neurological': 0, 'metabolic': 0,
                'cancer': 0, 'immune': 0, 'rare_diseases': 0
            }
        }
        
        api_delay = 0.15  # Moderate delay for comprehensive mode
        
        for variant in variants:
            try:
                # Comprehensive annotation
                annotation = await self.api_service.annotate_variant(str(variant.rsid))
                results['api_calls'] += 1
                
                if annotation:
                    await self._save_variant_annotation(session, variant, annotation, analysis_id, results['api_calls'])
                    
                    # Generate comprehensive insights
                    health_risk = await self.health_generator.generate_health_risk(variant, annotation)
                    if health_risk:
                        results['health_risks'].append(health_risk)
                    
                    drug_response = await self.drug_analyzer.analyze_variant(variant, annotation)
                    if drug_response:
                        results['drug_responses'].append(drug_response)
                    
                    # Specialized analysis
                    specialized_results = await self.specialized_analyzer.analyze_variant(variant, annotation)
                    for category, analysis_result in specialized_results.items():
                        if analysis_result:
                            results['specialized_profiles'][category] += 1
                
                results['processed'] += 1
                
                # Progress update every 10 variants
                if results['processed'] % 10 == 0:
                    progress = min(int((current_count + results['processed']) / total_count * 100), 99)
                    await self._update_analysis_status(
                        analysis_id, 'processing', progress,
                        f'Comprehensive processing {group_name}', current_count + results['processed']
                    )
                
                await asyncio.sleep(api_delay)
                
            except Exception as e:
                logger.error(f"❌ Comprehensive processing error for {variant.rsid}: {e}")
                results['processed'] += 1
        
        return results
    
    async def _save_variant_annotation(self, session: AsyncSession, variant, annotation: Dict, 
                                     analysis_id: int, api_call_number: int):
        """Save variant annotation data to database"""
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
    
    async def _finalize_analysis(self, session: AsyncSession, analysis_id: int, start_time: float,
                               processed_count: int, api_calls_made: int, health_risks: List,
                               drug_responses: List, specialized_profiles: Dict):
        """Finalize analysis and save results"""
        try:
            total_time = time.time() - start_time
            logger.info(f"🎉 Analysis {analysis_id} completed in {total_time:.2f}s")
            logger.info(f"📊 Processed {processed_count} variants with {api_calls_made} API calls")
            
            # Save health risks
            for risk_data in health_risks:
                health_risk = HealthRisk(**risk_data, analysis_id=analysis_id)
                session.add(health_risk)
            
            # Save drug responses  
            for drug_data in drug_responses:
                drug_response = DrugResponse(**drug_data, analysis_id=analysis_id)
                session.add(drug_response)
            
            await session.commit()
            
            # Final status update
            await self._update_analysis_status(
                analysis_id, 'completed', 100, 
                f'Analysis completed - {processed_count} variants processed', processed_count
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to finalize analysis: {e}")
            await session.rollback()