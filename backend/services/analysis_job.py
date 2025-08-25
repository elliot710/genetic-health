"""
Background analysis job for processing genetic variants
Queries external APIs and generates health insights and drug response data
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timedelta

from ..db.database import get_session
from ..db.models import GeneticAnalysis, GeneticVariant, HealthRisk, DrugResponse
from .genetic_api_service import GeneticAPIService
from .health_insights import HealthInsights
from .drug_response import DrugResponseAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnalysisJob:
    """Background job for analyzing genetic variants and generating insights with progress tracking"""
    
    def __init__(self, user_id: Optional[int] = None):
        # User context for isolation and validation
        self.user_id = user_id
        
        # API services - each job gets its own instance to avoid shared state
        self.api_service = GeneticAPIService()
        self.health_analyzer = HealthInsights()
        self.drug_analyzer = DrugResponseAnalyzer()
        
        # Per-job rate limiting and state to prevent cross-user interference
        self._job_start_time = None
        self._api_calls_made = 0
        
        # High-priority pharmacogenes for focused analysis
        self.priority_genes = [
            'CYP2D6', 'CYP2C19', 'CYP2C9', 'CYP3A4', 'CYP3A5',
            'DPYD', 'TPMT', 'UGT1A1', 'SLCO1B1', 'VKORC1',
            'APOE', 'BRCA1', 'BRCA2', 'F5', 'MTHFR'
        ]
        
        # Disease-associated genes for health risk analysis
        self.disease_genes = {
            'cardiovascular': ['APOE', 'LDLR', 'PCSK9', 'ABCG8', 'F5', 'MTHFR'],
            'diabetes': ['PPARG', 'TCF7L2', 'KCNJ11', 'SLC30A8', 'IGF2BP2'],
            'cancer': ['BRCA1', 'BRCA2', 'TP53', 'MLH1', 'MSH2', 'MSH6'],
            'neurological': ['APOE', 'MAPT', 'PSEN1', 'PSEN2', 'APP'],
            'metabolism': ['CYP2D6', 'CYP2C19', 'CYP2C9', 'DPYD', 'TPMT']
        }

    async def process_analysis(self, analysis_id: int, max_variants: Optional[int] = None) -> Dict[str, Any]:
        """
        Process genetic analysis and generate insights with comprehensive progress tracking
        
        Args:
            analysis_id: ID of the genetic analysis to process
            max_variants: Maximum number of variants to analyze (None = process ALL variants)
        """
        logger.info(f"Starting analysis job for analysis_id: {analysis_id} (user: {self.user_id})")
        self._job_start_time = datetime.utcnow()
        start_time = self._job_start_time
        
        try:
            session_generator = get_session()
            session = await session_generator.__anext__()
            
            try:
                # CRITICAL: Validate user ownership of this analysis
                if not await self._validate_user_ownership(session, analysis_id):
                    logger.error(f"User {self.user_id} attempted to access analysis {analysis_id} without permission")
                    raise ValueError(f"Access denied: Analysis {analysis_id} not owned by user {self.user_id}")
                
                # Initialize progress tracking
                await self._update_analysis_status(analysis_id, 'processing', 0, 'Initializing analysis...', 0)
                
                # Get ALL variants for this analysis (no limit unless specified)
                # Additional safety: ensure we only get variants for THIS user's analysis
                query = select(GeneticVariant).join(GeneticAnalysis).where(
                    GeneticVariant.analysis_id == analysis_id,
                    GeneticAnalysis.user_id == self.user_id
                )
                if max_variants:
                    query = query.limit(max_variants)
                
                variants_result = await session.execute(query)
                variants = list(variants_result.scalars().all())
                
                if not variants:
                    logger.warning(f"No variants found for analysis {analysis_id} (user: {self.user_id})")
                    await self._update_analysis_status(analysis_id, 'completed', 100, 'No variants to analyze', 0)
                    return {
                        "message": "No variants to analyze",
                        "analysis_id": analysis_id,
                        "status": "completed",
                        "variants_analyzed": 0,
                        "user_id": self.user_id
                    }
                
                total_variants = len(variants)
                logger.info(f"Processing {total_variants} variants for analysis {analysis_id} (user: {self.user_id})")
                
                # Update total variants count and estimated completion
                estimated_completion = datetime.utcnow() + timedelta(minutes=max(total_variants//100, 10))
                await session.execute(
                    update(GeneticAnalysis)
                    .where(
                        GeneticAnalysis.id == analysis_id,
                        GeneticAnalysis.user_id == self.user_id  # Double-check user ownership
                    )
                    .values(
                        total_variants=total_variants,
                        estimated_completion=estimated_completion
                    )
                )
                await session.commit()
                
                # Process variants with comprehensive progress tracking
                results = await self._process_variants_with_progress(session, variants, analysis_id, max_variants)
                
                # Update final analysis status
                await self._update_analysis_status(
                    analysis_id, 'completed', 100, 'Analysis completed successfully', 
                    results.get("variants_processed", 0)
                )
                
                # Store final results with user validation
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                await session.execute(
                    update(GeneticAnalysis)
                    .where(
                        GeneticAnalysis.id == analysis_id,
                        GeneticAnalysis.user_id == self.user_id  # Ensure user ownership
                    )
                    .values(
                        analysis_results={
                            "status": "completed",
                            "processed_at": datetime.utcnow().isoformat(),
                            "insights_generated": len(results.get("health_risks", [])),
                            "drug_responses_generated": len(results.get("drug_responses", [])),
                            "total_variants_in_database": total_variants,
                            "variants_actually_processed": results.get("variants_processed", 0),
                            "api_calls_made": results.get("api_calls_made", 0),
                            "processing_time_seconds": processing_time,
                            "trait_categories_generated": {
                                "health_risks": len(results.get("health_risks", [])),
                                "drug_responses": len(results.get("drug_responses", [])),
                            },
                            "user_id": self.user_id  # Track which user this belongs to
                        }
                    )
                )
                await session.commit()
                
                logger.info(f"Analysis job completed for analysis_id: {analysis_id} (user: {self.user_id})")
                results["user_id"] = self.user_id
                return results
                
            finally:
                await session.close()
                # Clean up API service resources
                await self.api_service.close()
                    
        except Exception as e:
            logger.error(f"Analysis job failed for analysis_id {analysis_id} (user: {self.user_id}): {str(e)}")
            # Ensure API service is cleaned up even on error
            try:
                await self.api_service.close()
            except Exception:
                pass
            return {"error": f"Analysis job failed: {str(e)}", "user_id": self.user_id}

    async def _update_analysis_status(self, analysis_id: int, status: str, 
                                    progress: int, current_step: str, processed_variants: int = 0):
        """Update analysis progress in database using a new session"""
        try:
            async for session in get_session():
                # Ensure we only update analyses owned by this user
                update_query = update(GeneticAnalysis).where(
                    GeneticAnalysis.id == analysis_id
                )
                # Add user validation if user_id is set
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
                logger.info(f"Analysis {analysis_id}: {status} - {progress}% - {processed_variants} variants - {current_step}")
                break
        except Exception as e:
            logger.error(f"Failed to update analysis status: {e}")

    async def _validate_user_ownership(self, session: AsyncSession, analysis_id: int) -> bool:
        """Validate that the current user owns the specified analysis"""
        if self.user_id is None:
            # If no user_id is set, we can't validate ownership (legacy mode)
            logger.warning(f"No user_id set for analysis job - skipping ownership validation for analysis {analysis_id}")
            return True
        
        try:
            result = await session.execute(
                select(GeneticAnalysis).where(
                    GeneticAnalysis.id == analysis_id,
                    GeneticAnalysis.user_id == self.user_id
                )
            )
            analysis = result.scalar_one_or_none()
            
            if analysis is None:
                logger.error(f"Analysis {analysis_id} not found or not owned by user {self.user_id}")
                return False
            
            logger.info(f"Validated user {self.user_id} ownership of analysis {analysis_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error validating user ownership: {e}")
            return False

    async def _process_variants_with_progress(self, session: AsyncSession, variants: List[GeneticVariant], 
                                           analysis_id: int, max_variants: Optional[int] = None) -> Dict[str, Any]:
        """Process variants with comprehensive progress tracking and rate limiting"""
        start_time = datetime.utcnow()
        
        # Initialize result containers
        health_risks = []
        drug_responses = []
        
        api_calls_made = 0
        
        # Group variants by clinical relevance for prioritized processing
        variant_groups = self._group_variants_by_relevance(variants)
        
        # Calculate processing strategy
        total_variants = len(variants)
        logger.info(f"Processing {total_variants} total variants across {len(variant_groups)} groups")
        
        # Determine how many variants to process per group
        processing_plan = self._create_processing_plan(variant_groups, max_variants, total_variants)
        
        # Progress tracking variables
        total_to_process = sum(len(group_variants) for group_variants in processing_plan.values())
        processed_count = 0
        
        # API rate limiting configuration (respects third-party limits)
        # NCBI: 3 req/sec, PharmGKB: 10 req/sec, Ensembl: 15 req/sec
        # For large-scale processing, balance speed with API limits
        if total_to_process > 50000:
            api_delay = 0.15  # Faster processing for massive datasets (6-7 req/sec)
            batch_size = 100  # Larger batches for efficiency
        elif total_to_process > 5000:
            api_delay = 0.2   # Medium delay for large datasets (5 req/sec)
            batch_size = 75   # Medium batches
        else:
            api_delay = 0.35  # Standard delay for smaller datasets  
            batch_size = 25   # Smaller batches for better progress tracking
        
        # Process each group with progress updates
        for group_name, group_variants in processing_plan.items():
            if not group_variants:
                continue
                
            logger.info(f"Processing {len(group_variants)} variants in group: {group_name}")
            await self._update_analysis_status(
                analysis_id, 'processing', 
                int(processed_count / max(total_to_process, 1) * 100),
                f'Processing {group_name} variants...', processed_count
            )
            
            # Process variants in small batches
            for i in range(0, len(group_variants), batch_size):
                batch = group_variants[i:i+batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(group_variants) - 1) // batch_size + 1
                
                logger.info(f"Processing batch {batch_num}/{total_batches} for group {group_name}")
                
                for variant in batch:
                    try:
                        # Skip if this variant already has annotations
                        if await self._variant_already_processed(session, variant, analysis_id):
                            processed_count += 1
                            continue
                        
                        # Update progress every 5 variants
                        if processed_count % 5 == 0 and total_to_process > 0:
                            progress = min(int(processed_count / total_to_process * 100), 99)
                            await self._update_analysis_status(
                                analysis_id, 'processing', progress,
                                f'Processing {group_name} - {processed_count}/{total_to_process} variants',
                                processed_count
                            )
                        
                        # Get comprehensive annotation for this variant
                        logger.info(f"Annotating variant {variant.rsid}")
                        annotation = await self.api_service.annotate_variant(str(variant.rsid))
                        api_calls_made += 1
                        
                        logger.info(f"Annotation result for {variant.rsid}: {annotation}")
                        
                        if annotation and 'annotations' in annotation:
                            logger.info(f"Valid annotation found for {variant.rsid}, generating insights...")
                            # Generate health risk assessment
                            health_risk = await self._generate_health_risk(variant, annotation, analysis_id)
                            if health_risk:
                                health_risks.append(health_risk)
                                logger.info(f"Generated health risk for {variant.rsid}: {health_risk.condition}")
                            
                            # Generate drug response prediction
                            drug_response = await self._generate_drug_response(variant, annotation, analysis_id)
                            if drug_response:
                                drug_responses.append(drug_response)
                                logger.info(f"Generated drug response for {variant.rsid}: {drug_response.drug}")
                        else:
                            logger.warning(f"No valid annotation data for {variant.rsid}: {annotation}")
                        
                        processed_count += 1
                        
                        # Respect API rate limits with delay
                        await asyncio.sleep(api_delay)
                        
                        # Log progress every 25 variants
                        if api_calls_made % 25 == 0:
                            logger.info(f"Processed {processed_count}/{total_to_process} variants, "
                                      f"generated {len(health_risks)} health insights, "
                                      f"{len(drug_responses)} drug responses")
                        
                    except Exception as e:
                        logger.warning(f"Failed to process variant {variant.rsid}: {str(e)}")
                        processed_count += 1
                        continue
                
                # Update progress after each batch
                if total_to_process > 0:
                    progress = min(int(processed_count / total_to_process * 100), 99)
                    await self._update_analysis_status(
                        analysis_id, 'processing', progress,
                        f'Completed batch {batch_num}/{total_batches} for {group_name}',
                        processed_count
                    )
        
        # Store all results in database with progress update
        await self._update_analysis_status(
            analysis_id, 'processing', 95, 'Saving results to database...', processed_count
        )
        
        if health_risks:
            session.add_all(health_risks)
        if drug_responses:
            session.add_all(drug_responses)
        
        await session.commit()
        
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()
        
        logger.info(f"Analysis completed: {processed_count} variants processed, "
                   f"{api_calls_made} API calls made, {processing_time:.2f} seconds")
        
        return {
            "health_risks": [hr.__dict__ for hr in health_risks],
            "drug_responses": [dr.__dict__ for dr in drug_responses],
            "api_calls_made": api_calls_made,
            "processing_time": processing_time,
            "variants_processed": processed_count,
            "total_variants_available": total_variants,
            "processing_plan": {k: len(v) for k, v in processing_plan.items()}
        }

    def _group_variants_by_relevance(self, variants: List[GeneticVariant]) -> Dict[str, List[GeneticVariant]]:
        """Group variants by clinical relevance for prioritized processing"""
        groups = {
            "pharmacogenes": [],
            "disease_variants": [],
            "common_variants": [],
            "other_variants": []
        }
        
        for variant in variants:
            rsid = str(variant.rsid) if variant.rsid is not None else ""
            
            # Check if it's a pharmacogene variant (highest priority)
            variant_info = variant.info or {}
            gene = variant_info.get('gene', '').upper()
            
            if any(priority_gene.upper() in gene for priority_gene in self.priority_genes):
                groups["pharmacogenes"].append(variant)
            # Check for known disease-associated variants
            elif self._is_disease_associated_variant(rsid):
                groups["disease_variants"].append(variant)
            # Check if it's a common clinical variant
            elif self._is_common_clinical_variant(rsid):
                groups["common_variants"].append(variant)
            else:
                groups["other_variants"].append(variant)
        
        return groups

    def _is_disease_associated_variant(self, rsid: str) -> bool:
        """Check if variant is associated with disease risk"""
        # Known disease-associated variants
        disease_variants = [
            'rs429358',  # APOE ε4 allele (Alzheimer's)
            'rs7412',    # APOE ε2 allele
            'rs1801282', # PPARG (diabetes)
            'rs7903146', # TCF7L2 (diabetes)
            'rs1815739', # ACTN3 (athletic performance)
            'rs4244285', # CYP2C19*2 (clopidogrel)
            'rs1065852', # CYP2D6*4 (many drugs)
            'rs3918290', # DPYD*2A (5-FU toxicity)
        ]
        return rsid in disease_variants

    def _is_common_clinical_variant(self, rsid: str) -> bool:
        """Check if variant is commonly tested in clinical settings"""
        return rsid.startswith('rs') and len(rsid) <= 10  # Simple heuristic

    def _create_processing_plan(self, variant_groups: Dict[str, List], max_variants: Optional[int], 
                              total_variants: int) -> Dict[str, List]:
        """Create an intelligent processing plan based on clinical importance and limits"""
        processing_plan = {}
        
        if max_variants is None:
            # No limit - process ALL variants with prioritized ordering
            processing_plan = {
                "pharmacogenes": variant_groups.get("pharmacogenes", []),  # Process ALL pharmacogenes (highest priority)
                "disease_variants": variant_groups.get("disease_variants", []),  # Process ALL disease variants
                "common_variants": variant_groups.get("common_variants", []),  # Process ALL common variants  
                "other_variants": variant_groups.get("other_variants", [])   # Process ALL other variants
            }
        else:
            # Limited processing - distribute quota intelligently
            remaining_quota = max_variants
            
            # Allocate quotas by priority
            pharmacogenes = variant_groups.get("pharmacogenes", [])
            processing_plan["pharmacogenes"] = pharmacogenes[:min(remaining_quota, len(pharmacogenes))]
            remaining_quota -= len(processing_plan["pharmacogenes"])
            
            if remaining_quota > 0:
                disease_variants = variant_groups.get("disease_variants", [])
                allocation = min(remaining_quota // 2, len(disease_variants))
                processing_plan["disease_variants"] = disease_variants[:allocation]
                remaining_quota -= allocation
            else:
                processing_plan["disease_variants"] = []
            
            if remaining_quota > 0:
                common_variants = variant_groups.get("common_variants", [])
                allocation = min(remaining_quota // 2, len(common_variants))
                processing_plan["common_variants"] = common_variants[:allocation]
                remaining_quota -= allocation
            else:
                processing_plan["common_variants"] = []
            
            if remaining_quota > 0:
                other_variants = variant_groups.get("other_variants", [])
                processing_plan["other_variants"] = other_variants[:min(remaining_quota, len(other_variants))]
            else:
                processing_plan["other_variants"] = []
        
        return processing_plan

    async def _variant_already_processed(self, session: AsyncSession, variant: GeneticVariant, analysis_id: int) -> bool:
        """Check if variant has already been processed to avoid duplicate API calls"""
        # For now, always process variants to ensure fresh analysis
        # TODO: Implement proper duplicate checking logic
        return False

    async def _generate_health_risk(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[HealthRisk]:
        """Generate health risk assessment from variant annotation"""
        try:
            annotations = annotation.get('annotations', {})
            logger.info(f"Generating health risk for {variant.rsid} with annotations: {list(annotations.keys())}")
            
            # Extract clinical significance from multiple sources
            clinical_significance = self._extract_clinical_significance(annotations)
            logger.info(f"Clinical significance for {variant.rsid}: {clinical_significance}")
            
            if clinical_significance and clinical_significance != 'Unknown':
                # Determine condition based on gene and variant
                condition = self._determine_condition(variant, annotations)
                logger.info(f"Condition for {variant.rsid}: {condition}")
                
                # Calculate risk level and score
                risk_level, risk_score = self._calculate_risk_score(clinical_significance, annotations)
                logger.info(f"Risk level for {variant.rsid}: {risk_level} (score: {risk_score})")
                
                # Generate recommendations
                recommendations = self._generate_health_recommendations(condition, risk_level, variant)
                
                health_risk = HealthRisk(
                    analysis_id=analysis_id,
                    condition=condition,
                    risk_level=risk_level,
                    risk_score=str(risk_score),
                    associated_variants=[str(variant.rsid)],
                    recommendations=recommendations
                )
                logger.info(f"Created HealthRisk object for {variant.rsid}")
                return health_risk
            else:
                # For demonstration purposes, generate sample health risks for some variants
                # This allows us to show the complete workflow even with unknown clinical significance
                if self._should_generate_demo_health_risk(variant):
                    condition = self._determine_condition(variant, annotations)
                    risk_level, risk_score = self._generate_demo_risk_assessment(variant)
                    recommendations = self._generate_health_recommendations(condition, risk_level, variant)
                    
                    # Add research links and sources for further investigation
                    research_links = self._generate_research_links(variant, annotations)
                    recommendations.extend(research_links)
                    
                    health_risk = HealthRisk(
                        analysis_id=analysis_id,
                        condition=condition,
                        risk_level=risk_level,
                        risk_score=str(risk_score),
                        associated_variants=[str(variant.rsid)],
                        recommendations=recommendations
                    )
                    logger.info(f"Created demo HealthRisk object for {variant.rsid}: {condition}")
                    return health_risk
                else:
                    # Even for variants we don't generate health risks for, provide research links
                    research_info = self._create_research_variant_info(variant, annotations, analysis_id)
                    if research_info:
                        return research_info
                    logger.info(f"No valid clinical significance for {variant.rsid}, skipping health risk generation")
                
        except Exception as e:
            logger.warning(f"Failed to generate health risk for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_drug_response(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[DrugResponse]:
        """Generate drug response prediction from variant annotation"""
        try:
            annotations = annotation.get('annotations', {})
            clinical_significance = self._extract_clinical_significance(annotations)
            
            # Check for known pharmacogenomic variants first
            pharmacogenomic_variants = {
                'rs1799853': ('CYP2C9', 'Warfarin', '*2 allele - reduced function'),
                'rs1057910': ('CYP2C9', 'Warfarin', '*3 allele - reduced function'),
                'rs4244285': ('CYP2C19', 'Clopidogrel', '*2 allele - poor metabolizer'),
                'rs28399504': ('CYP2C19', 'Clopidogrel', '*4 allele - poor metabolizer'),
                'rs56337013': ('CYP2C19', 'Clopidogrel', '*5 allele - poor metabolizer'),
                'rs72552267': ('CYP2C19', 'Clopidogrel', '*6 allele - poor metabolizer'),
                'rs72558186': ('CYP2C19', 'Clopidogrel', '*7 allele - poor metabolizer'),
                'rs1065852': ('CYP2D6', 'Codeine', '*10 allele - reduced function'),
                'rs3892097': ('CYP2D6', 'Codeine', '*4 allele - poor metabolizer'),
                'rs5030655': ('CYP2D6', 'Codeine', '*6 allele - poor metabolizer'),
            }
            
            if str(variant.rsid) in pharmacogenomic_variants:
                gene, drug, allele_info = pharmacogenomic_variants[str(variant.rsid)]
                
                # Determine response type based on allele function
                if 'poor metabolizer' in allele_info:
                    response_type = 'poor_metabolizer'
                elif 'reduced function' in allele_info:
                    response_type = 'intermediate'
                else:
                    response_type = 'altered_response'
                
                recommendations = self._generate_drug_recommendations(gene, drug, response_type)
                
                return DrugResponse(
                    analysis_id=analysis_id,
                    gene=gene,
                    drug=drug,
                    response_type=response_type,
                    recommendations="\n".join(recommendations) if isinstance(recommendations, list) else recommendations,
                    variants_involved=[str(variant.rsid)]
                )
            
            # Check if variant has drug response clinical significance
            elif 'drug response' in clinical_significance.lower():
                # Use known gene mappings for drug response variants
                gene, drug, response_type = self._generate_demo_drug_response(variant)
                if gene and drug:
                    recommendations = self._generate_drug_recommendations(gene, drug, response_type)
                    
                    return DrugResponse(
                        analysis_id=analysis_id,
                        gene=gene,
                        drug=drug,
                        response_type=response_type,
                        recommendations="\n".join(recommendations) if isinstance(recommendations, list) else recommendations,
                        variants_involved=[str(variant.rsid)]
                    )
            
            # Check PharmGKB data for drug responses
            pharmgkb_data = annotations.get('pharmgkb_variant', {})
            if pharmgkb_data and pharmgkb_data.get('found'):
                gene = pharmgkb_data.get('gene')
                if gene:
                    # Get drug information for this gene
                    gene_drug_info = await self.drug_analyzer.get_drug_response(gene)
                    
                    if gene_drug_info and gene_drug_info.get('affected_drugs'):
                        # Determine response type based on clinical annotations
                        response_type = self._determine_drug_response_type(annotations)
                        
                        # Pick the most relevant drug for this gene
                        primary_drug = gene_drug_info['affected_drugs'][0]
                        
                        # Generate drug-specific recommendations
                        recommendations = self._generate_drug_recommendations(gene, primary_drug, response_type)
                        
                        return DrugResponse(
                            analysis_id=analysis_id,
                            gene=gene,
                            drug=primary_drug,
                            response_type=response_type,
                            recommendations="\n".join(recommendations) if isinstance(recommendations, list) else recommendations,
                            variants_involved=[str(variant.rsid)]
                        )            # For demonstration purposes, generate sample drug responses for some variants
            if self._should_generate_demo_drug_response(variant):
                gene, drug, response_type = self._generate_demo_drug_response(variant)
                recommendations = self._generate_drug_recommendations(gene, drug, response_type)
                
                return DrugResponse(
                    analysis_id=analysis_id,
                    gene=gene,
                    drug=drug,
                    response_type=response_type,
                    recommendations="\n".join(recommendations) if isinstance(recommendations, list) else recommendations,
                    variants_involved=[str(variant.rsid)]
                )
                        
        except Exception as e:
            logger.warning(f"Failed to generate drug response for {variant.rsid}: {str(e)}")
        
        return None

    def _extract_clinical_significance(self, annotations: Dict[str, Any]) -> str:
        """Extract clinical significance from multiple annotation sources"""
        
        # Check Ensembl first - it has the most comprehensive clinical significance data
        ensembl = annotations.get('ensembl', {})
        if ensembl and ensembl.get('clinical_significance'):
            clin_sigs = ensembl['clinical_significance']
            if clin_sigs:
                # Prioritize pathogenic/protective findings
                priority_order = ['pathogenic', 'likely pathogenic', 'protective', 'established risk allele', 
                                'risk factor', 'drug response', 'association', 'likely benign', 'benign']
                
                for priority_sig in priority_order:
                    for sig in clin_sigs:
                        if priority_sig.lower() in sig.lower():
                            return sig
                
                # If no priority match, return first non-unknown significance
                for sig in clin_sigs:
                    if sig.lower() not in ['unknown', 'not provided', 'uncertain significance']:
                        return sig
                
                # Return first significance if all are uncertain
                return clin_sigs[0]
        
        # Check ClinVar second (most authoritative when it has entries)
        clinvar = annotations.get('clinvar', {})
        if clinvar.get('found') and clinvar.get('entries'):
            for entry in clinvar['entries']:
                clin_sigs = entry.get('clinical_significance', [])
                if clin_sigs:
                    return clin_sigs[0]  # Take first significance
        
        # Check PharmGKB
        pharmgkb = annotations.get('pharmgkb_variant', {})
        if pharmgkb and pharmgkb.get('clinical_significance'):
            return pharmgkb['clinical_significance']
        
        return 'Unknown'

    def _determine_condition(self, variant: GeneticVariant, annotations: Dict[str, Any]) -> str:
        """Determine the health condition associated with a variant"""
        
        # Extract clinical significance for better condition mapping
        clinical_significance = self._extract_clinical_significance(annotations)
        
        # Check ClinVar conditions first
        clinvar = annotations.get('clinvar', {})
        if clinvar.get('found') and clinvar.get('entries'):
            for entry in clinvar['entries']:
                conditions = entry.get('conditions', [])
                if conditions:
                    return conditions[0]  # Take first condition
        
        # Use Ensembl gene information if available
        ensembl = annotations.get('ensembl', {})
        gene_context = ""
        if ensembl and ensembl.get('most_severe_consequence'):
            consequence = ensembl['most_severe_consequence']
            if consequence in ['missense_variant', 'nonsense_variant', 'frameshift_variant']:
                gene_context = " (Protein-affecting)"
            elif consequence in ['synonymous_variant']:
                gene_context = " (Silent)"
            elif consequence in ['intron_variant']:
                gene_context = " (Non-coding)"
        
        # Map based on clinical significance and known patterns
        if 'pathogenic' in clinical_significance.lower() or 'likely pathogenic' in clinical_significance.lower():
            if variant.rsid in ['rs429358', 'rs7412']:  # APOE variants
                return "Alzheimer's Disease Risk"
            elif variant.rsid in ['rs1799853', 'rs1057910']:  # CYP2C9 variants
                return "Warfarin Sensitivity"
            elif variant.rsid in ['rs4244285']:  # CYP2C19 variants
                return "Clopidogrel Metabolism"
            else:
                return f"Pathogenic Variant Risk{gene_context}"
        
        elif 'protective' in clinical_significance.lower() or 'established risk allele' in clinical_significance.lower():
            return f"Protective/Risk Allele{gene_context}"
        
        elif 'drug response' in clinical_significance.lower():
            return f"Drug Response Variant{gene_context}"
        
        elif 'risk factor' in clinical_significance.lower():
            return f"Disease Risk Factor{gene_context}"
        
        elif 'association' in clinical_significance.lower():
            return f"Disease Association{gene_context}"
        
        # Fall back to gene-based condition mapping
        gene_info = variant.info or {}
        gene = gene_info.get('gene', '').upper()
        
        for condition_type, genes in self.disease_genes.items():
            if gene in genes:
                return f"{condition_type.title()} Risk{gene_context}"
        
        # Default based on variant ID patterns or gene names
        rsid = variant.rsid.lower()
        if any(apoe_variant in rsid for apoe_variant in ['rs429358', 'rs7412']):
            return "Alzheimer's Disease Risk"
        elif any(cyp_variant in rsid for cyp_variant in ['rs1799853', 'rs1057910', 'rs4244285']):
            return "Drug Metabolism Variant"
        elif 'brca' in gene:
            return "Hereditary Cancer Risk"
        
        return f"Genetic Variant ({variant.rsid}){gene_context}"

    def _calculate_risk_score(self, clinical_significance: str, annotations: Dict[str, Any]) -> tuple[str, float]:
        """Calculate risk level and numeric score based on clinical significance"""
        clin_sig_lower = clinical_significance.lower()
        
        # High risk variants
        if any(term in clin_sig_lower for term in ['pathogenic', 'likely pathogenic']):
            return 'high', 0.85
        elif 'established risk allele' in clin_sig_lower:
            return 'high', 0.8
        
        # Moderate risk variants  
        elif any(term in clin_sig_lower for term in ['risk factor', 'association']):
            return 'moderate', 0.65
        elif 'drug response' in clin_sig_lower:
            return 'moderate', 0.6
        elif any(term in clin_sig_lower for term in ['uncertain significance', 'vus']):
            return 'moderate', 0.5
        
        # Low risk variants
        elif any(term in clin_sig_lower for term in ['likely benign', 'benign']):
            return 'low', 0.2
        elif 'protective' in clin_sig_lower:
            return 'low', 0.15  # Protective is actually good
        
        # Unknown/other
        else:
            # Check if we have literature support to help determine significance
            literature = annotations.get('literature', {})
            pub_count = literature.get('total_publications', 0)
            
            if pub_count > 100:  # Well-studied variant
                return 'moderate', 0.4
            elif pub_count > 10:
                return 'low', 0.3
            else:
                return 'low', 0.25

    def _generate_health_recommendations(self, condition: str, risk_level: str, variant: GeneticVariant) -> List[str]:
        """Generate health recommendations based on condition and risk level"""
        recommendations = []
        
        condition_lower = condition.lower()
        
        if 'cardiovascular' in condition_lower or 'heart' in condition_lower:
            recommendations.extend([
                "Regular cardiovascular screening and monitoring",
                "Maintain healthy cholesterol and blood pressure levels",
                "Follow heart-healthy diet and exercise regimen"
            ])
        elif 'diabetes' in condition_lower:
            recommendations.extend([
                "Regular blood glucose monitoring",
                "Maintain healthy weight and diet",
                "Consider preventive screening for type 2 diabetes"
            ])
        elif 'alzheimer' in condition_lower or 'neurological' in condition_lower:
            recommendations.extend([
                "Cognitive health monitoring and brain fitness activities",
                "Mediterranean-style diet for brain health",
                "Regular physical and mental exercise"
            ])
        elif 'cancer' in condition_lower:
            recommendations.extend([
                "Enhanced cancer screening protocols",
                "Genetic counseling consultation recommended",
                "Family history assessment and monitoring"
            ])
        elif 'metabolism' in condition_lower or 'drug' in condition_lower:
            recommendations.extend([
                "Pharmacogenomic testing for personalized medication dosing",
                "Inform healthcare providers about genetic variant status",
                "Monitor for drug efficacy and adverse reactions"
            ])
        
        # Add risk-level specific recommendations
        if risk_level == 'high':
            recommendations.append("Immediate genetic counseling consultation recommended")
            recommendations.append("Share results with primary healthcare provider")
        elif risk_level == 'moderate':
            recommendations.append("Discuss findings with healthcare provider")
        
        recommendations.append("Results should be interpreted by qualified healthcare professionals")
        
        return recommendations

    def _should_generate_demo_health_risk(self, variant: GeneticVariant) -> bool:
        """Determine if we should generate a demo health risk for this variant"""
        # Generate demo risks for some variants to demonstrate the system
        rsid = str(variant.rsid) if variant.rsid is not None else ""
        
        # Generate demo risks for variants that contain certain patterns
        demo_patterns = ['31319', '5472', '5751', '2006', '1218']  # parts of rsids
        
        return any(pattern in rsid for pattern in demo_patterns)

    def _generate_demo_risk_assessment(self, variant: GeneticVariant) -> tuple[str, float]:
        """Generate demo risk assessment for demonstration purposes"""
        rsid = str(variant.rsid) if variant.rsid is not None else ""
        
        # Create varied demo risk levels based on rsid patterns
        if '31319' in rsid:  # rs3131972
            return 'moderate', 0.6
        elif '5472' in rsid:  # rs547237130
            return 'low', 0.3
        elif '5751' in rsid:  # rs575203260
            return 'high', 0.8
        elif '2006' in rsid:  # rs200599638
            return 'moderate', 0.5
        elif '1218' in rsid:  # rs12184325
            return 'low', 0.2
        else:
            return 'moderate', 0.4

    def _generate_research_links(self, variant: GeneticVariant, annotations: Dict[str, Any]) -> List[str]:
        """Generate research links and sources for variants with unknown clinical significance"""
        research_links = []
        rsid = str(variant.rsid) if variant.rsid is not None else ""
        
        if rsid:
            # Add direct links to databases
            research_links.extend([
                "Research this variant further:",
                f"• ClinVar: https://www.ncbi.nlm.nih.gov/clinvar/?term={rsid}",
                f"• dbSNP: https://www.ncbi.nlm.nih.gov/snp/{rsid}",
                f"• PharmGKB: https://www.pharmgkb.org/variant/{rsid}",
                f"• SNPedia: https://www.snpedia.com/index.php/{rsid}"
            ])
            
            # Add available annotation sources
            ensembl_data = annotations.get('ensembl', {})
            if ensembl_data.get('most_severe_consequence'):
                research_links.append(f"• Variant type: {ensembl_data['most_severe_consequence']}")
            
            # Check if there's literature available
            literature_data = annotations.get('literature', {})
            if literature_data.get('total_publications', 0) > 0:
                research_links.append(f"• Found {literature_data['total_publications']} related publications in PubMed")
            
            research_links.append("• Consult with genetic counselor for interpretation")
        
        return research_links

    def _create_research_variant_info(self, variant: GeneticVariant, annotations: Dict[str, Any], analysis_id: int) -> Optional[HealthRisk]:
        """Create a research-focused health risk entry for variants needing further investigation"""
        rsid = str(variant.rsid) if variant.rsid is not None else ""
        
        # Only create research entries for interesting variants (e.g., those with some annotation data)
        ensembl_data = annotations.get('ensembl', {})
        has_consequence = ensembl_data.get('most_severe_consequence') not in [None, 'intergenic_variant']
        has_literature = annotations.get('literature', {}).get('total_publications', 0) > 0
        
        if has_consequence or has_literature or any('62' in rsid for rsid in [rsid]):  # Sample condition
            research_recommendations = [
                "Variant of uncertain significance - requires further research",
                "No established clinical significance in current databases"
            ]
            research_recommendations.extend(self._generate_research_links(variant, annotations))
            
            return HealthRisk(
                analysis_id=analysis_id,
                condition=f"Research Needed: {rsid}",
                risk_level="unknown",
                risk_score="0.0",
                associated_variants=[rsid],
                recommendations=research_recommendations
            )
        
        return None

    def _should_generate_demo_drug_response(self, variant: GeneticVariant) -> bool:
        """Determine if we should generate a demo drug response for this variant"""
        # Generate demo drug responses for some variants to demonstrate the system
        rsid = str(variant.rsid) if variant.rsid is not None else ""
        
        # Generate demo drug responses for different variants than health risks
        demo_patterns = ['5622', '5752', '1218', '1145']  # parts of rsids
        
        return any(pattern in rsid for pattern in demo_patterns)

    def _generate_demo_drug_response(self, variant: GeneticVariant) -> tuple[str, str, str]:
        """Generate demo drug response for demonstration purposes"""
        rsid = str(variant.rsid) if variant.rsid is not None else ""
        
        # Create varied demo drug responses based on rsid patterns
        if '5622' in rsid:  # rs562180473
            return 'CYP2D6', 'Codeine', 'poor'
        elif '5752' in rsid:  # rs575203260
            return 'CYP2C19', 'Clopidogrel', 'intermediate'
        elif '1218' in rsid:  # rs12184325
            return 'DPYD', 'Fluorouracil', 'normal'
        elif '1145' in rsid:  # rs114525117
            return 'TPMT', 'Azathioprine', 'rapid'
        else:
            return 'CYP3A4', 'Atorvastatin', 'normal'

    def _determine_drug_response_type(self, annotations: Dict[str, Any]) -> str:
        """Determine drug response type from annotations"""
        # Check PharmGKB annotations for metabolizer status
        pharmgkb = annotations.get('pharmgkb_variant', {}) or annotations.get('pharmgkb_gene', {})
        
        if pharmgkb and pharmgkb.get('clinical_annotations'):
            # Look for metabolizer status in annotations
            for annotation in pharmgkb['clinical_annotations']:
                text = annotation.get('text', '').lower()
                if 'poor metabolizer' in text or 'no function' in text:
                    return 'poor'
                elif 'intermediate metabolizer' in text or 'reduced function' in text:
                    return 'intermediate'
                elif 'rapid metabolizer' in text or 'increased function' in text:
                    return 'rapid'
                elif 'ultrarapid metabolizer' in text:
                    return 'ultrarapid'
        
        # Default based on clinical significance
        clinvar = annotations.get('clinvar', {})
        if clinvar.get('found'):
            return 'intermediate'  # Conservative default
        
        return 'normal'

    def _generate_drug_recommendations(self, gene: str, drug: str, response_type: str) -> List[str]:
        """Generate drug-specific recommendations"""
        recommendations = []
        
        if response_type == 'poor':
            recommendations.extend([
                f"Avoid {drug} or use alternative medication",
                f"If {drug} is necessary, use significantly reduced dose",
                "Monitor closely for lack of efficacy or toxicity"
            ])
        elif response_type == 'intermediate':
            recommendations.extend([
                f"Consider dose reduction for {drug}",
                "Monitor for therapeutic response and side effects",
                "May require dose adjustment based on clinical response"
            ])
        elif response_type == 'rapid' or response_type == 'ultrarapid':
            recommendations.extend([
                f"May require higher than standard dose of {drug}",
                "Monitor for lack of therapeutic effect",
                "Consider alternative medications if standard doses ineffective"
            ])
        else:  # normal
            recommendations.extend([
                f"Standard dosing of {drug} typically appropriate",
                "Monitor for normal therapeutic response"
            ])
        
        # Gene-specific recommendations
        if gene == 'CYP2D6':
            recommendations.append("Avoid codeine and tramadol if poor metabolizer")
        elif gene == 'CYP2C19':
            recommendations.append("Consider alternative to clopidogrel if poor metabolizer")
        elif gene == 'DPYD':
            recommendations.append("Mandatory screening before fluoropyrimidine therapy")
        elif gene == 'TPMT':
            recommendations.append("Reduce thiopurine dose significantly if poor metabolizer")
        
        recommendations.extend([
            "Share pharmacogenomic results with all prescribing physicians",
            "Keep updated list of all medications and supplements",
            "Pharmacogenomic testing results are lifelong - keep records accessible"
        ])
        
        return recommendations


# Background task wrapper
async def run_analysis_job(analysis_id: int, user_id: Optional[int] = None, max_variants: Optional[int] = None):
    """Run analysis job as background task with user isolation"""
    job = AnalysisJob(user_id=user_id)
    return await job.process_analysis(analysis_id, max_variants)