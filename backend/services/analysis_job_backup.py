"""
Background analysis job for processing genetic variants
Queries external APIs and generates health insights and drug response data
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime

from ..db.database import get_session
from ..db.models import (
    GeneticAnalysis, GeneticVariant, HealthRisk, DrugResponse,
    PhysicalTrait, NutritionTrait, SportsPerformance, CognitiveProfile,
    PersonalityTrait, AncestryResult, CarrierStatus, WellnessMetric,
    MethylationProfile, DetoxificationProfile
)
from .genetic_api_service import GeneticAPIService
from .health_insights import HealthInsights
from .drug_response import DrugResponseAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnalysisJob:
    """Background job for analyzing genetic variants and generating insights"""
    
    def __init__(self):
        self.api_service = GeneticAPIService()
        self.health_analyzer = HealthInsights()
        self.drug_analyzer = DrugResponseAnalyzer()
        
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
from ..db.models import (
    GeneticAnalysis, GeneticVariant, HealthRisk, DrugResponse,
    PhysicalTrait, NutritionTrait, SportsPerformance, CognitiveProfile,
    PersonalityTrait, AncestryResult, CarrierStatus, WellnessMetric,
    MethylationProfile, DetoxificationProfile
)
from .genetic_api_service import GeneticAPIService
from .health_insights import HealthInsights
from .drug_response import DrugResponseAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

    def _group_variants_by_relevance(self, variants: List[GeneticVariant]) -> Dict[str, List[GeneticVariant]]:
        """Group variants by clinical relevance for prioritized processing"""
        groups = {
            "pharmacogenes": [],
            "disease_variants": [],
            "common_variants": [],
            "other_variants": []
        }
        
        for variant in variants:
            rsid = str(variant.rsid)
            
            # Check if it's a pharmacogene variant (highest priority)
            if any(gene.lower() in (variant.info or {}).get('gene', '').lower() for gene in self.priority_genes):
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
        # Known disease-associated variants (this would typically come from a database)
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
        # This would typically query a clinical variant database
        return rsid.startswith('rs') and len(rsid) <= 10  # Simple heuristic

    async def _generate_health_risk(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[HealthRisk]:
        """Generate health risk assessment from variant annotation"""
        try:
            annotations = annotation.get('annotations', {})
            
            # Extract clinical significance from multiple sources
            clinical_significance = self._extract_clinical_significance(annotations)
            
            if clinical_significance and clinical_significance != 'Unknown':
                # Determine condition based on gene and variant
                condition = self._determine_condition(variant, annotations)
                
                # Calculate risk level and score
                risk_level, risk_score = self._calculate_risk_score(clinical_significance, annotations)
                
                # Generate recommendations
                recommendations = self._generate_health_recommendations(condition, risk_level, variant)
                
                return HealthRisk(
                    analysis_id=analysis_id,
                    condition=condition,
                    risk_level=risk_level,
                    risk_score=str(risk_score),  # Convert float to string
                    associated_variants=[variant.rsid],
                    recommendations=recommendations
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate health risk for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_drug_response(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[DrugResponse]:
        """Generate drug response prediction from variant annotation"""
        try:
            annotations = annotation.get('annotations', {})
            
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
                            recommendations=recommendations,
                            variants_involved=[str(variant.rsid)]
                        )
                        
        except Exception as e:
            logger.warning(f"Failed to generate drug response for {variant.rsid}: {str(e)}")
        
        return None

    def _extract_clinical_significance(self, annotations: Dict[str, Any]) -> str:
        """Extract clinical significance from multiple annotation sources"""
        # Check ClinVar first (most authoritative)
        clinvar = annotations.get('clinvar', {})
        if clinvar.get('found') and clinvar.get('entries'):
            for entry in clinvar['entries']:
                clin_sigs = entry.get('clinical_significance', [])
                if clin_sigs:
                    return clin_sigs[0]  # Take first significance
        
        # Check Ensembl
        ensembl = annotations.get('ensembl', {})
        if ensembl and ensembl.get('clinical_significance'):
            return ensembl['clinical_significance'][0] if ensembl['clinical_significance'] else 'Unknown'
        
        # Check PharmGKB
        pharmgkb = annotations.get('pharmgkb_variant', {})
        if pharmgkb and pharmgkb.get('clinical_significance'):
            return pharmgkb['clinical_significance']
        
        return 'Unknown'

    def _determine_condition(self, variant: GeneticVariant, annotations: Dict[str, Any]) -> str:
        """Determine the health condition associated with a variant"""
        # Check ClinVar conditions
        clinvar = annotations.get('clinvar', {})
        if clinvar.get('found') and clinvar.get('entries'):
            for entry in clinvar['entries']:
                conditions = entry.get('conditions', [])
                if conditions:
                    return conditions[0]  # Take first condition
        
        # Fall back to gene-based condition mapping
        gene_info = variant.info or {}
        gene = gene_info.get('gene', '').upper()
        
        for condition_type, genes in self.disease_genes.items():
            if gene in genes:
                return f"{condition_type.title()} Risk"
        
        # Default based on variant ID patterns
        if 'APOE' in gene:
            return "Alzheimer's Disease Risk"
        elif any(cyp in gene for cyp in ['CYP2D6', 'CYP2C19', 'CYP2C9']):
            return "Drug Metabolism Variant"
        elif 'BRCA' in gene:
            return "Hereditary Cancer Risk"
        
        return f"Genetic Variant ({variant.rsid})"

    def _calculate_risk_score(self, clinical_significance: str, annotations: Dict[str, Any]) -> tuple[str, float]:
        """Calculate risk level and numeric score"""
        clin_sig_lower = clinical_significance.lower()
        
        if any(term in clin_sig_lower for term in ['pathogenic', 'likely pathogenic']):
            return 'high', 0.8
        elif any(term in clin_sig_lower for term in ['risk factor', 'association']):
            return 'moderate', 0.6
        elif any(term in clin_sig_lower for term in ['benign', 'likely benign']):
            return 'low', 0.2
        elif 'uncertain' in clin_sig_lower or 'vus' in clin_sig_lower:
            return 'moderate', 0.5
        else:
            return 'moderate', 0.4

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

    def _variant_already_processed(self, session: AsyncSession, variant: GeneticVariant, analysis_id: int) -> bool:
        """Check if variant has already been processed to avoid duplicate API calls"""
        # For now, assume all variants need processing
        # In future, could check if health_risks or drug_responses already exist for this variant
        return False

    async def _generate_all_traits(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int,
                                 health_risks: List, drug_responses: List, physical_traits: List,
                                 nutrition_traits: List, sports_performance: List, cognitive_profiles: List,
                                 personality_traits: List, ancestry_results: List, carrier_status: List,
                                 wellness_metrics: List, methylation_profiles: List, detox_profiles: List):
        """Generate all possible traits for a variant and add to respective lists"""
        
        # Generate health risk assessments
        health_risk = await self._generate_health_risk(variant, annotation, analysis_id)
        if health_risk:
            health_risks.append(health_risk)
        
        # Generate drug response predictions
        drug_response = await self._generate_drug_response(variant, annotation, analysis_id)
        if drug_response:
            drug_responses.append(drug_response)
        
        # Generate physical traits
        physical_trait = await self._generate_physical_trait(variant, annotation, analysis_id)
        if physical_trait:
            physical_traits.append(physical_trait)
        
        # Generate nutrition insights
        nutrition_trait = await self._generate_nutrition_trait(variant, annotation, analysis_id)
        if nutrition_trait:
            nutrition_traits.append(nutrition_trait)
        
        # Generate sports performance insights
        sports_trait = await self._generate_sports_performance(variant, annotation, analysis_id)
        if sports_trait:
            sports_performance.append(sports_trait)
        
        # Generate cognitive insights
        cognitive_trait = await self._generate_cognitive_profile(variant, annotation, analysis_id)
        if cognitive_trait:
            cognitive_profiles.append(cognitive_trait)
        
        # Generate personality insights
        personality_trait = await self._generate_personality_trait(variant, annotation, analysis_id)
        if personality_trait:
            personality_traits.append(personality_trait)
        
        # Generate ancestry insights
        ancestry_trait = await self._generate_ancestry_result(variant, annotation, analysis_id)
        if ancestry_trait:
            ancestry_results.append(ancestry_trait)
        
        # Generate carrier status
        carrier_trait = await self._generate_carrier_status(variant, annotation, analysis_id)
        if carrier_trait:
            carrier_status.append(carrier_trait)
        
        # Generate wellness metrics
        wellness_trait = await self._generate_wellness_metric(variant, annotation, analysis_id)
        if wellness_trait:
            wellness_metrics.append(wellness_trait)
        
        # Generate methylation insights
        methylation_trait = await self._generate_methylation_profile(variant, annotation, analysis_id)
        if methylation_trait:
            methylation_profiles.append(methylation_trait)
        
        # Generate detox insights
        detox_trait = await self._generate_detox_profile(variant, annotation, analysis_id)
        if detox_trait:
            detox_profiles.append(detox_trait)

    async def _generate_physical_trait(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[PhysicalTrait]:
        """Generate physical trait analysis from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known physical trait variants
            trait_variants = {
                'rs1426654': {'trait': 'Skin Pigmentation', 'category': 'appearance'},
                'rs12913832': {'trait': 'Eye Color', 'category': 'appearance'},
                'rs4778138': {'trait': 'Hair Color', 'category': 'appearance'},
                'rs1815739': {'trait': 'Fast-twitch Muscle Fibers', 'category': 'athletic'},
                'rs713598': {'trait': 'Bitter Taste Sensitivity', 'category': 'sensory'},
                'rs1726866': {'trait': 'Height Influence', 'category': 'physical'}
            }
            
            if rsid in trait_variants:
                trait_info = trait_variants[rsid]
                
                return PhysicalTrait(
                    analysis_id=analysis_id,
                    trait_name=trait_info['trait'],
                    trait_category=trait_info['category'],
                    genetic_result=self._determine_trait_result(variant, rsid),
                    confidence='moderate',
                    associated_variants=[rsid],
                    description=f"Genetic influence on {trait_info['trait'].lower()}"
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate physical trait for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_nutrition_trait(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[NutritionTrait]:
        """Generate nutrition trait analysis from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known nutrition-related variants
            nutrition_variants = {
                'rs1801133': {'nutrient': 'Folate', 'type': 'slow'},
                'rs1799853': {'nutrient': 'Vitamin K', 'type': 'sensitive'},
                'rs4680': {'nutrient': 'Caffeine', 'type': 'slow'},
                'rs708272': {'nutrient': 'Alcohol', 'type': 'fast'},
                'rs4988235': {'nutrient': 'Lactose', 'type': 'intolerant'}
            }
            
            if rsid in nutrition_variants:
                nutrient_info = nutrition_variants[rsid]
                
                return NutritionTrait(
                    analysis_id=analysis_id,
                    nutrient=nutrient_info['nutrient'],
                    metabolism_type=nutrient_info['type'],
                    dietary_recommendations=self._get_nutrition_recommendations(nutrient_info['nutrient'], nutrient_info['type']),
                    associated_variants=[rsid],
                    sensitivity_level='moderate'
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate nutrition trait for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_sports_performance(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[SportsPerformance]:
        """Generate sports performance analysis from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known sports performance variants
            sports_variants = {
                'rs1815739': {'category': 'power', 'advantage': 'high'},
                'rs4994': {'category': 'endurance', 'advantage': 'moderate'},
                'rs8192678': {'category': 'recovery', 'advantage': 'high'},
                'rs1799752': {'category': 'endurance', 'advantage': 'moderate'}
            }
            
            if rsid in sports_variants:
                sports_info = sports_variants[rsid]
                
                return SportsPerformance(
                    analysis_id=analysis_id,
                    performance_category=sports_info['category'],
                    genetic_advantage=sports_info['advantage'],
                    sport_recommendations=self._get_sports_recommendations(sports_info['category']),
                    associated_variants=[rsid],
                    training_advice=f"Focus on {sports_info['category']} training"
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate sports performance for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_cognitive_profile(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[CognitiveProfile]:
        """Generate cognitive profile from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known cognitive variants
            cognitive_variants = {
                'rs4680': {'domain': 'working_memory', 'score': 'high'},
                'rs429358': {'domain': 'memory', 'score': 'low'},
                'rs6265': {'domain': 'learning', 'score': 'moderate'},
                'rs1800497': {'domain': 'processing_speed', 'score': 'moderate'}
            }
            
            if rsid in cognitive_variants:
                cognitive_info = cognitive_variants[rsid]
                
                return CognitiveProfile(
                    analysis_id=analysis_id,
                    cognitive_domain=cognitive_info['domain'],
                    genetic_score=cognitive_info['score'],
                    percentile=self._calculate_cognitive_percentile(cognitive_info['score']),
                    associated_variants=[rsid],
                    enhancement_suggestions=self._get_cognitive_enhancement(cognitive_info['domain'])
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate cognitive profile for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_methylation_profile(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[MethylationProfile]:
        """Generate methylation profile from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known methylation variants
            methylation_variants = {
                'rs1801133': {'gene': 'MTHFR', 'variant': 'C677T', 'capacity': 'reduced'},
                'rs1801131': {'gene': 'MTHFR', 'variant': 'A1298C', 'capacity': 'reduced'},
                'rs4680': {'gene': 'COMT', 'variant': 'Val158Met', 'capacity': 'slow'},
                'rs1805087': {'gene': 'MTR', 'variant': 'A2756G', 'capacity': 'normal'},
                'rs1801394': {'gene': 'MTRR', 'variant': 'A66G', 'capacity': 'normal'}
            }
            
            if rsid in methylation_variants:
                methyl_info = methylation_variants[rsid]
                
                return MethylationProfile(
                    analysis_id=analysis_id,
                    gene=methyl_info['gene'],
                    variant=methyl_info['variant'],
                    methylation_capacity=methyl_info['capacity'],
                    supplement_recommendations=self._get_methylation_supplements(methyl_info['gene'], methyl_info['capacity']),
                    associated_variants=[rsid]
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate methylation profile for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_detox_profile(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[DetoxificationProfile]:
        """Generate detoxification profile from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known detox variants
            detox_variants = {
                'rs1065852': {'phase': 'phase1', 'gene': 'CYP2D6', 'capacity': 'slow'},
                'rs4244285': {'phase': 'phase1', 'gene': 'CYP2C19', 'capacity': 'slow'},
                'rs1799853': {'phase': 'phase1', 'gene': 'CYP2C9', 'capacity': 'slow'},
                'rs1695': {'phase': 'phase2', 'gene': 'GSTP1', 'capacity': 'normal'},
                'rs4986893': {'phase': 'phase1', 'gene': 'CYP2C19', 'capacity': 'fast'}
            }
            
            if rsid in detox_variants:
                detox_info = detox_variants[rsid]
                
                return DetoxificationProfile(
                    analysis_id=analysis_id,
                    detox_phase=detox_info['phase'],
                    gene=detox_info['gene'],
                    detox_capacity=detox_info['capacity'],
                    toxin_sensitivity=self._calculate_toxin_sensitivity(detox_info['capacity']),
                    support_recommendations=self._get_detox_support(detox_info['phase'], detox_info['capacity']),
                    associated_variants=[rsid]
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate detox profile for {variant.rsid}: {str(e)}")
        
        return None

    def _determine_trait_result(self, variant: GeneticVariant, rsid: str) -> str:
        """Determine trait result based on genotype"""
        genotype = variant.genotype or 'Unknown'
        
        # Simple mapping based on common patterns
        if rsid == 'rs12913832':  # Eye color
            if 'AA' in genotype:
                return 'Brown eyes likely'
            elif 'GG' in genotype:
                return 'Blue eyes likely'
            else:
                return 'Mixed eye color'
        
        return f"Genetic variant present ({genotype})"

    def _get_nutrition_recommendations(self, nutrient: str, metabolism_type: str) -> List[str]:
        """Get nutrition recommendations based on nutrient and metabolism"""
        recommendations = []
        
        if nutrient == 'Folate' and metabolism_type == 'slow':
            recommendations = ['Consider methylfolate supplementation', 'Increase leafy greens intake']
        elif nutrient == 'Caffeine' and metabolism_type == 'slow':
            recommendations = ['Limit caffeine intake', 'Avoid caffeine after 2 PM']
        elif nutrient == 'Lactose' and metabolism_type == 'intolerant':
            recommendations = ['Consider lactase supplements', 'Choose lactose-free dairy products']
        else:
            recommendations = [f'Monitor {nutrient} intake', 'Maintain balanced diet']
        
        return recommendations

    def _get_sports_recommendations(self, category: str) -> List[str]:
        """Get sports recommendations based on performance category"""
        recommendations = {
            'power': ['Focus on explosive training', 'Weight lifting', 'Sprint training'],
            'endurance': ['Long-distance running', 'Cycling', 'Swimming'],
            'recovery': ['Prioritize sleep', 'Active recovery sessions', 'Proper nutrition timing']
        }
        return recommendations.get(category, ['General fitness training'])

    def _calculate_cognitive_percentile(self, score: str) -> int:
        """Calculate cognitive percentile based on genetic score"""
        percentiles = {
            'high': 85,
            'moderate': 60,
            'low': 35
        }
        return percentiles.get(score, 50)

    def _get_cognitive_enhancement(self, domain: str) -> List[str]:
        """Get cognitive enhancement suggestions"""
        suggestions = {
            'working_memory': ['Practice memory games', 'Meditation', 'Regular exercise'],
            'memory': ['Spaced repetition learning', 'Adequate sleep', 'Omega-3 supplements'],
            'learning': ['Active learning techniques', 'Regular breaks', 'Variety in study methods'],
            'processing_speed': ['Brain training games', 'Regular physical exercise', 'Mindfulness practice']
        }
        return suggestions.get(domain, ['General cognitive training'])

    def _get_methylation_supplements(self, gene: str, capacity: str) -> List[str]:
        """Get methylation supplement recommendations"""
        supplements = []
        
        if gene == 'MTHFR' and capacity == 'reduced':
            supplements = ['Methylfolate', 'B12 (methylcobalamin)', 'B6']
        elif gene == 'COMT' and capacity == 'slow':
            supplements = ['SAMe', 'Magnesium', 'B6']
        else:
            supplements = ['B-complex', 'Folate']
        
        return supplements

    def _calculate_toxin_sensitivity(self, capacity: str) -> str:
        """Calculate toxin sensitivity based on detox capacity"""
        sensitivity_map = {
            'slow': 'high',
            'impaired': 'very_high',
            'fast': 'low',
            'normal': 'moderate'
        }
        return sensitivity_map.get(capacity, 'moderate')

    def _get_detox_support(self, phase: str, capacity: str) -> List[str]:
        """Get detox support recommendations"""
        recommendations = []
        
        if phase == 'phase1':
            if capacity in ['slow', 'impaired']:
                recommendations = ['Avoid alcohol', 'Limit processed foods', 'Support with B vitamins']
            else:
                recommendations = ['Antioxidant support', 'Green tea', 'Cruciferous vegetables']
        elif phase == 'phase2':
            if capacity in ['slow', 'impaired']:
                recommendations = ['NAC supplementation', 'Glutathione support', 'Milk thistle']
            else:
                recommendations = ['Maintain fiber intake', 'Stay hydrated', 'Regular exercise']
        
        return recommendations

    async def _generate_personality_trait(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[PersonalityTrait]:
        """Generate personality trait analysis from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known personality variants
            personality_variants = {
                'rs4680': {'trait': 'Risk Taking', 'dimension': 'openness', 'influence': 'moderate'},
                'rs25531': {'trait': 'Anxiety Sensitivity', 'dimension': 'neuroticism', 'influence': 'high'},
                'rs6265': {'trait': 'Learning Style', 'dimension': 'conscientiousness', 'influence': 'moderate'},
                'rs1800497': {'trait': 'Reward Seeking', 'dimension': 'extraversion', 'influence': 'moderate'}
            }
            
            if rsid in personality_variants:
                trait_info = personality_variants[rsid]
                
                return PersonalityTrait(
                    analysis_id=analysis_id,
                    trait_name=trait_info['trait'],
                    personality_dimension=trait_info['dimension'],
                    genetic_influence=trait_info['influence'],
                    associated_variants=[rsid],
                    behavioral_insights=self._get_behavioral_insights(trait_info['trait'])
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate personality trait for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_ancestry_result(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[AncestryResult]:
        """Generate ancestry analysis from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known ancestry informative markers
            ancestry_variants = {
                'rs1426654': {'population': 'European', 'region': 'Northern Europe', 'confidence': 'high'},
                'rs3827760': {'population': 'East Asian', 'region': 'East Asia', 'confidence': 'moderate'},
                'rs16891982': {'population': 'African', 'region': 'Sub-Saharan Africa', 'confidence': 'high'},
                'rs12913832': {'population': 'European', 'region': 'Northern Europe', 'confidence': 'moderate'}
            }
            
            if rsid in ancestry_variants:
                ancestry_info = ancestry_variants[rsid]
                
                return AncestryResult(
                    analysis_id=analysis_id,
                    population_group=ancestry_info['population'],
                    geographic_region=ancestry_info['region'],
                    confidence_level=ancestry_info['confidence'],
                    associated_variants=[rsid],
                    migration_patterns=self._get_migration_patterns(ancestry_info['population'])
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate ancestry result for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_carrier_status(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[CarrierStatus]:
        """Generate carrier status analysis from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known carrier variants
            carrier_variants = {
                'rs113993960': {'condition': 'Cystic Fibrosis', 'inheritance': 'autosomal_recessive'},
                'rs5030868': {'condition': 'Sickle Cell Disease', 'inheritance': 'autosomal_recessive'},
                'rs80338943': {'condition': 'Tay-Sachs Disease', 'inheritance': 'autosomal_recessive'},
                'rs28939670': {'condition': 'Phenylketonuria', 'inheritance': 'autosomal_recessive'}
            }
            
            if rsid in carrier_variants:
                carrier_info = carrier_variants[rsid]
                
                return CarrierStatus(
                    analysis_id=analysis_id,
                    condition_name=carrier_info['condition'],
                    carrier_risk='possible',
                    inheritance_pattern=carrier_info['inheritance'],
                    associated_variants=[rsid],
                    genetic_counseling_recommended=True
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate carrier status for {variant.rsid}: {str(e)}")
        
        return None

    async def _generate_wellness_metric(self, variant: GeneticVariant, annotation: Dict[str, Any], analysis_id: int) -> Optional[WellnessMetric]:
        """Generate wellness metric analysis from variant"""
        try:
            rsid = str(variant.rsid)
            
            # Known wellness variants
            wellness_variants = {
                'rs1801133': {'category': 'stress_response', 'metric': 'Stress Resilience', 'impact': 'moderate'},
                'rs4680': {'category': 'sleep', 'metric': 'Sleep Quality', 'impact': 'moderate'},
                'rs6265': {'category': 'mood', 'metric': 'Mood Stability', 'impact': 'high'},
                'rs25531': {'category': 'stress_response', 'metric': 'Anxiety Tendency', 'impact': 'high'}
            }
            
            if rsid in wellness_variants:
                wellness_info = wellness_variants[rsid]
                
                return WellnessMetric(
                    analysis_id=analysis_id,
                    wellness_category=wellness_info['category'],
                    metric_name=wellness_info['metric'],
                    genetic_impact=wellness_info['impact'],
                    improvement_strategies=self._get_wellness_strategies(wellness_info['category']),
                    associated_variants=[rsid]
                )
                
        except Exception as e:
            logger.warning(f"Failed to generate wellness metric for {variant.rsid}: {str(e)}")
        
        return None

    def _get_behavioral_insights(self, trait: str) -> List[str]:
        """Get behavioral insights for personality traits"""
        insights = {
            'Risk Taking': ['May be more open to new experiences', 'Could benefit from structured decision-making'],
            'Anxiety Sensitivity': ['May be more sensitive to stress', 'Stress management techniques beneficial'],
            'Learning Style': ['May prefer hands-on learning', 'Benefits from varied learning approaches'],
            'Reward Seeking': ['May be motivated by immediate rewards', 'Goal-setting strategies helpful']
        }
        return insights.get(trait, ['Individual variation is significant'])

    def _get_migration_patterns(self, population: str) -> List[str]:
        """Get historical migration patterns for population groups"""
        patterns = {
            'European': ['Migration out of Africa 70,000 years ago', 'Settlement in Europe 45,000 years ago'],
            'East Asian': ['Migration through Central Asia', 'Settlement in East Asia 40,000 years ago'],
            'African': ['Originated in Africa', 'Multiple migration events within continent'],
            'Native American': ['Migration across Bering land bridge', 'Settlement in Americas 15,000 years ago']
        }
        return patterns.get(population, ['Complex migration history'])

    def _get_wellness_strategies(self, category: str) -> List[str]:
        """Get wellness improvement strategies"""
        strategies = {
            'stress_response': ['Regular meditation or mindfulness practice', 'Stress management techniques', 'Adequate sleep'],
            'sleep': ['Sleep hygiene practices', 'Regular sleep schedule', 'Avoid caffeine before bed'],
            'mood': ['Regular exercise', 'Social connections', 'Professional support if needed'],
            'anxiety': ['Relaxation techniques', 'Cognitive behavioral strategies', 'Professional guidance']
        }
        return strategies.get(category, ['General wellness practices'])

# Background task wrapper
async def run_analysis_job(analysis_id: int, max_variants: Optional[int] = None):
    """Run analysis job as background task"""
    job = AnalysisJob()
    return await job.process_analysis(analysis_id, max_variants)