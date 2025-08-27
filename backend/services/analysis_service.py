"""
Simplified genetic analysis service with fast-only processing.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from ..db.models import GeneticAnalysis, AnalysisVariant, VariantAnnotation
from ..core.exceptions import (
    AnalysisNotFoundException
)
from ..core.config import settings

logger = logging.getLogger(__name__)


class AnalysisStrategy(Enum):
    """Analysis processing strategy - optimized for fast processing."""
    FAST = "fast"          # Optimized processing for speed


@dataclass
class AnalysisProgress:
    """Data class for tracking analysis progress."""
    total_variants: int
    processed_variants: int
    current_step: str
    status: str
    estimated_completion: Optional[datetime] = None
    
    @property
    def progress_percentage(self) -> int:
        if self.total_variants == 0:
            return 0
        return min(100, int((self.processed_variants / self.total_variants) * 100))


@dataclass
class AnalysisResult:
    """Result of genetic analysis processing."""
    analysis_id: int
    status: str
    processed_variants: int
    total_variants: int
    api_calls_made: int
    processing_time: float
    strategy_used: str
    errors: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class ProgressTracker:
    """Tracks and updates analysis progress."""
    
    def __init__(self, analysis_id: int, total_variants: int):
        self.analysis_id = analysis_id
        self.total_variants = total_variants
        self.processed_variants = 0
        self.start_time = time.time()
        self.last_update = 0
        
    async def update_progress(
        self,
        processed_variants: int,
        current_step: str,
        status: str = "processing"
    ):
        """Update analysis progress in database."""
        self.processed_variants = processed_variants
        
        # Rate limit updates to avoid too many database writes
        current_time = time.time()
        if current_time - self.last_update < 2.0:  # Update max every 2 seconds
            return
            
        self.last_update = current_time
        
        progress_percentage = self.progress_percentage
        
        # Estimate completion time
        elapsed_time = current_time - self.start_time
        if processed_variants > 0:
            time_per_variant = elapsed_time / processed_variants
            remaining_variants = self.total_variants - processed_variants
            estimated_seconds = remaining_variants * time_per_variant
            estimated_completion = datetime.now() + timedelta(seconds=estimated_seconds)
        else:
            estimated_completion = None
        
        try:
            from ..db.database import async_session_factory
            async with async_session_factory() as session:
                await session.execute(
                    update(GeneticAnalysis)
                    .where(GeneticAnalysis.id == self.analysis_id)
                    .values(
                        progress_percentage=progress_percentage,
                        processed_variants=processed_variants,
                        current_step=current_step,
                        analysis_status=status,
                        estimated_completion=estimated_completion
                    )
                )
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
    
    @property
    def progress_percentage(self) -> int:
        if self.total_variants == 0:
            return 0
        return min(100, int((self.processed_variants / self.total_variants) * 100))


class GeneticAnalysisService:
    """
    Simplified genetic analysis service with fast-only processing.
    Uses dependency injection and async context management.
    """
    
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        self.api_service = None
        self.health_service = None
        self.drug_service = None
        self.specialized_service = None
        
    async def initialize_services(self):
        """Initialize dependent services."""
        try:
            from ..services.genetic_api_service import OptimizedGeneticAPIService
            from ..services.health_insights import HealthInsights
            from ..services.drug_response import DrugResponseAnalyzer
            from ..services.specialized_analyzers import SpecializedAnalyzerManager
            
            self.api_service = OptimizedGeneticAPIService()
            await self.api_service.initialize()
            
            self.health_service = HealthInsights()
            self.drug_service = DrugResponseAnalyzer()
            self.specialized_service = SpecializedAnalyzerManager()
            
        except ImportError as e:
            logger.warning(f"Some services not available: {e}")
    
    async def process_analysis(
        self,
        analysis_id: int,
        strategy: AnalysisStrategy = AnalysisStrategy.FAST
    ) -> AnalysisResult:
        """
        Process genetic analysis with fast-only strategy.
        """
        start_time = time.time()
        
        try:
            # Initialize services
            await self.initialize_services()
            
            # Load analysis data
            analysis, variants = await self._load_analysis_data(analysis_id)
            
            if not variants:
                logger.warning(f"No variants found for analysis {analysis_id}")
                return AnalysisResult(
                    analysis_id=analysis_id,
                    status="completed",
                    processed_variants=0,
                    total_variants=0,
                    api_calls_made=0,
                    processing_time=time.time() - start_time,
                    strategy_used=strategy.value,
                    errors=["No variants found"]
                )
            
            # Initialize progress tracker
            progress_tracker = ProgressTracker(analysis_id, len(variants))
            
            logger.info(f"Starting fast analysis for {len(variants)} variants")
            
            # Process variants with fast strategy
            processed_count, api_calls, errors = await self._process_variants_fast(
                variants, analysis_id, progress_tracker
            )
            
            # Update final status
            final_status = "completed" if not errors else "completed_with_errors"
            await progress_tracker.update_progress(
                processed_count,
                f"Completed - {processed_count}/{len(variants)} variants processed",
                final_status
            )
            
            processing_time = time.time() - start_time
            
            logger.info(f"Analysis {analysis_id} completed in {processing_time:.2f}s")
            
            return AnalysisResult(
                analysis_id=analysis_id,
                status=final_status,
                processed_variants=processed_count,
                total_variants=len(variants),
                api_calls_made=api_calls,
                processing_time=processing_time,
                strategy_used=strategy.value,
                errors=errors
            )
            
        except Exception as e:
            logger.error(f"Analysis {analysis_id} failed: {str(e)}")
            
            # Update status to failed
            try:
                await ProgressTracker(analysis_id, 0).update_progress(
                    0, f"Failed: {str(e)}", "failed"
                )
            except Exception:
                pass
            
            return AnalysisResult(
                analysis_id=analysis_id,
                status="failed",
                processed_variants=0,
                total_variants=0,
                api_calls_made=0,
                processing_time=time.time() - start_time,
                errors=[str(e)],
                strategy_used=strategy.value
            )
        
        finally:
            try:
                if self.api_service:
                    await self.api_service.close()
            except Exception:
                pass
    
    async def _load_analysis_data(self, analysis_id: int) -> tuple[GeneticAnalysis, List[AnalysisVariant]]:
        """Load analysis and analysis variants from database."""
        from ..db.database import async_session_factory
        
        async with async_session_factory() as session:
            query = select(GeneticAnalysis).options(
                selectinload(GeneticAnalysis.analysis_variants)
            ).where(GeneticAnalysis.id == analysis_id)
            
            if self.user_id is not None:
                query = query.where(GeneticAnalysis.user_id == self.user_id)
            
            result = await session.execute(query)
            analysis = result.scalar_one_or_none()
            
            if not analysis:
                raise AnalysisNotFoundException(
                    f"Analysis {analysis_id} not found for user {self.user_id}"
                )
            
            return analysis, analysis.analysis_variants
    
    async def _process_variants_fast(
        self,
        analysis_variants: List[AnalysisVariant],
        analysis_id: int,
        progress_tracker: ProgressTracker
    ) -> tuple[int, int, List[str]]:
        """Fast processing - optimized for speed with resume capability."""
        processed_count = 0
        api_calls_made = 0
        errors = []
        
        # Fast processing settings
        batch_size = settings.analysis.default_batch_size * 2  # Larger batches for speed
        max_concurrent = settings.api.max_concurrent
        api_delay = settings.api.base_delay * 0.5  # Reduced delay for speed
        
        logger.info(f"Fast processing: {len(analysis_variants)} variants in batches of {batch_size}")
        
        from ..db.database import async_session_factory
        async with async_session_factory() as session:
            # RESUME LOGIC: Check for existing annotations to avoid reprocessing
            existing_annotations_query = await session.execute(
                select(VariantAnnotation.analysis_variant_id).where(VariantAnnotation.analysis_id == analysis_id)
            )
            processed_variant_ids = {row[0] for row in existing_annotations_query.fetchall()}
            already_processed_count = len(processed_variant_ids)
            
            logger.info(f"🔄 RESUMING: Found {already_processed_count} already processed variants")
            
            # Update starting progress
            processed_count = already_processed_count
            if already_processed_count > 0:
                initial_progress = int(already_processed_count / len(analysis_variants) * 100)
                await progress_tracker.update_progress(
                    already_processed_count,
                    current_step=f"Resuming from {already_processed_count} processed variants",
                )
                logger.info(f"📊 Starting from {initial_progress}% progress ({already_processed_count}/{len(analysis_variants)} variants)")
            
            # Process in batches
            for i in range(0, len(analysis_variants), batch_size):
                batch = analysis_variants[i:i + batch_size]
                
                # Filter out already processed variants
                new_variants_in_batch = [av for av in batch if av.id not in processed_variant_ids]
                
                if not new_variants_in_batch:
                    logger.info(f"⏭️ Batch {i//batch_size + 1}: All variants already processed, skipping")
                    continue
                
                logger.info(f"🧬 Batch {i//batch_size + 1}: Processing {len(new_variants_in_batch)}/{len(batch)} new variants")
                
                # Process batch concurrently with semaphore for rate limiting
                semaphore = asyncio.Semaphore(max_concurrent)
                tasks = []
                
                for analysis_variant in new_variants_in_batch:
                    # Get the variant's rsid for processing
                    rsid = getattr(analysis_variant, 'rsid', None)
                    if rsid:  # Only process variants with rsid
                        task = self._process_single_variant_fast(analysis_variant, analysis_id, session, semaphore)
                        tasks.append(task)
                
                # Execute batch concurrently
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in results:
                        if isinstance(result, Exception):
                            errors.append(str(result))
                        elif result:
                            api_calls_made += 1
                            processed_count += 1
                
                # Update progress
                await progress_tracker.update_progress(
                    processed_count,
                    current_step=f"fast_processing_batch_{i//batch_size + 1}",
                )
                
                # Commit batch
                await session.commit()
                
                # Minimal delay between batches for speed
                if i + batch_size < len(analysis_variants):
                    await asyncio.sleep(api_delay)
        
        return processed_count, api_calls_made, errors
    
    async def _process_single_variant_fast(
        self,
        analysis_variant: AnalysisVariant,
        analysis_id: int,
        session: AsyncSession,
        semaphore: asyncio.Semaphore
    ) -> bool:
        """Process a single variant with fast approach."""
        async with semaphore:
            try:
                # Check if already processed (double-check to avoid race conditions)
                existing_check = await session.execute(
                    select(VariantAnnotation).where(
                        VariantAnnotation.analysis_variant_id == analysis_variant.id,
                        VariantAnnotation.analysis_id == analysis_id
                    )
                )
                if existing_check.scalar_one_or_none():
                    logger.info(f"⏭️ Variant {analysis_variant.rsid} already processed, skipping")
                    return False
                
                if not self.api_service:
                    return False
                    
                # Fast annotation - minimal data only
                annotation = await self.api_service.annotate_variant(str(analysis_variant.rsid))
                if annotation:
                    await self._save_variant_annotation_fast(session, analysis_variant, annotation, analysis_id)
                    logger.info(f"✅ Processed NEW variant: {analysis_variant.rsid}")
                    return True
                    
            except Exception as e:
                logger.warning(f"Failed to process variant {analysis_variant.rsid}: {e}")
                
        return False
    
    async def _save_variant_annotation_fast(
        self,
        session: AsyncSession,
        variant: AnalysisVariant,  # Now using AnalysisVariant directly
        annotation: Dict[str, Any],
        analysis_id: int
    ):
        """Save variant annotation with minimal data for speed."""
        try:
            # Save annotation data to the appropriate JSON fields based on source
            annotation_record = VariantAnnotation(
                analysis_id=analysis_id,
                analysis_variant_id=variant.id,  # Now using AnalysisVariant ID
                rsid=variant.rsid,
                ensembl_data={
                    "consequence": annotation.get("consequence"),
                    "gene": annotation.get("gene"),
                    "impact": annotation.get("impact"),
                    "source": "fast_processing"
                } if annotation else None,
                annotation_status='completed'
            )
            
            session.add(annotation_record)
            
        except Exception as e:
            logger.error(f"Failed to save annotation for {variant.rsid}: {e}")


# Legacy wrapper for backward compatibility
async def process_genetic_analysis(analysis_id: int, user_id: int) -> Dict[str, Any]:
    """
    Legacy function wrapper for backward compatibility.
    """
    try:
        service = GeneticAnalysisService(user_id)
        result = await service.process_analysis(analysis_id, AnalysisStrategy.FAST)
        
        return {
            "success": True,
            "analysis_id": result.analysis_id,
            "status": result.status,
            "processed_variants": result.processed_variants,
            "total_variants": result.total_variants,
            "processing_time": result.processing_time,
            "errors": result.errors
        }
        
    except Exception as e:
        logger.error(f"Legacy analysis wrapper failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "analysis_id": analysis_id
        }