"""
Refactored specialized genetic analyzers with clean interfaces and optimized performance.
"""
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    MethylationProfile, DetoxificationProfile, SportsPerformance
)
from .analyzer_interfaces import BaseAnalyzer, AnalysisContext, analyzer_registry

logger = logging.getLogger(__name__)


class MethylationAnalyzer(BaseAnalyzer):
    """Analyzes methylation pathway variants."""
    
    def __init__(self):
        super().__init__()
        self.methylation_genes = {
            'MTHFR': {
                'variants': ['rs1801133', 'rs1801131'],
                'pathways': ['folate_metabolism', 'homocysteine_metabolism'],
            },
            'COMT': {
                'variants': ['rs4680'],
                'pathways': ['dopamine_metabolism', 'stress_response'],
            },
            'MTR': {
                'variants': ['rs1805087'],
                'pathways': ['methionine_cycle', 'b12_metabolism'],
            },
            'MTRR': {
                'variants': ['rs1801394'],
                'pathways': ['methionine_cycle', 'b12_recycling'],
            },
            'CBS': {
                'variants': ['rs234706', 'rs2851391'],
                'pathways': ['transsulfuration', 'homocysteine_metabolism'],
            }
        }
        
        self.supplement_recommendations = {
            'mthfr_variant': ['methylfolate', 'methylcobalamin', 'riboflavin', 'betaine'],
            'comt_slow': ['magnesium', 'sam_e', 'green_tea_extract'],
            'comt_fast': ['quercetin', 'luteolin', 'comt_inhibitors'],
            'mtr_variant': ['methylcobalamin', 'folate', 'betaine'],
            'cbs_upregulation': ['molybdenum', 'yucca_root', 'reduce_sulfur_foods'],
            'general_support': ['b_complex', 'magnesium', 'zinc', 'methylfolate']
        }
    
    def get_analyzer_name(self) -> str:
        return "methylation"
    
    async def can_analyze(self, context: AnalysisContext) -> bool:
        """Check if variant affects methylation pathways."""
        rsid = str(context.analysis_variant.rsid)
        
        for gene, gene_info in self.methylation_genes.items():
            if self.is_rsid_in_variant_list(rsid, gene_info['variants']):
                return True
        
        return False
    
    async def analyze(self, context: AnalysisContext) -> Optional[MethylationProfile]:
        """Generate methylation profile."""
        try:
            rsid = str(context.analysis_variant.rsid)
            affected_gene = None
            
            for gene, gene_info in self.methylation_genes.items():
                if self.is_rsid_in_variant_list(rsid, gene_info['variants']):
                    affected_gene = gene
                    break
            
            if not affected_gene:
                return None
            
            clinical_significance = self.extract_clinical_significance(context.annotation)
            methylation_capacity = self._assess_methylation_capacity(affected_gene, rsid, clinical_significance)
            supplements = self._generate_methylation_supplements(affected_gene, methylation_capacity)
            
            profile = MethylationProfile(
                analysis_id=context.analysis_id,
                gene=affected_gene,
                variant=rsid,
                methylation_capacity=methylation_capacity,
                supplement_recommendations=supplements,
                associated_variants=[rsid]
            )
            
            context.session.add(profile)
            logger.info(f"Generated methylation profile for {affected_gene} variant {rsid}")
            return profile
            
        except Exception as e:
            logger.error(f"Error generating methylation profile for {context.analysis_variant.rsid}: {e}")
            return None
    
    def _assess_methylation_capacity(self, gene: str, rsid: str, clinical_significance: str) -> str:
        """Assess methylation capacity based on gene variant."""
        if gene == 'MTHFR':
            if rsid == 'rs1801133' and 'pathogenic' in clinical_significance.lower():
                return 'severely_reduced'
            elif rsid == 'rs1801133':
                return 'reduced'
            elif rsid == 'rs1801131':
                return 'mildly_reduced'
        elif gene == 'COMT':
            if 'slow' in clinical_significance.lower():
                return 'slow_processing'
            elif 'fast' in clinical_significance.lower():
                return 'fast_processing'
            else:
                return 'intermediate_processing'
        elif gene in ['MTR', 'MTRR']:
            return 'b12_dependent' if 'variant' in clinical_significance.lower() else 'normal'
        elif gene == 'CBS':
            return 'upregulated' if 'upregulation' in clinical_significance.lower() else 'normal'
        
        return 'normal'
    
    def _generate_methylation_supplements(self, gene: str, capacity: str) -> List[str]:
        """Generate supplement recommendations."""
        recommendations = []
        
        if gene == 'MTHFR' and 'reduced' in capacity:
            recommendations.extend(self.supplement_recommendations['mthfr_variant'])
        elif gene == 'COMT':
            if 'slow' in capacity:
                recommendations.extend(self.supplement_recommendations['comt_slow'])
            elif 'fast' in capacity:
                recommendations.extend(self.supplement_recommendations['comt_fast'])
        elif gene in ['MTR', 'MTRR'] and 'b12' in capacity:
            recommendations.extend(self.supplement_recommendations['mtr_variant'])
        elif gene == 'CBS' and 'upregulated' in capacity:
            recommendations.extend(self.supplement_recommendations['cbs_upregulation'])
        
        recommendations.extend(self.supplement_recommendations['general_support'][:2])
        return list(set(recommendations))


class DetoxificationAnalyzer(BaseAnalyzer):
    """Analyzes detoxification pathway variants."""
    
    def __init__(self):
        super().__init__()
        self.detox_genes = {
            'CYP1A1': {'phase': 'phase1', 'function': 'polycyclic_aromatic_hydrocarbons'},
            'CYP1A2': {'phase': 'phase1', 'function': 'caffeine_metabolism'},
            'CYP2D6': {'phase': 'phase1', 'function': 'drug_metabolism'},
            'CYP2C9': {'phase': 'phase1', 'function': 'warfarin_metabolism'},
            'CYP2C19': {'phase': 'phase1', 'function': 'drug_metabolism'},
            'CYP3A4': {'phase': 'phase1', 'function': 'drug_metabolism'},
            'GSTM1': {'phase': 'phase2', 'function': 'glutathione_conjugation'},
            'GSTT1': {'phase': 'phase2', 'function': 'glutathione_conjugation'},
            'GSTP1': {'phase': 'phase2', 'function': 'glutathione_conjugation'},
            'UGT1A1': {'phase': 'phase2', 'function': 'glucuronidation'},
            'NAT1': {'phase': 'phase2', 'function': 'acetylation'},
            'NAT2': {'phase': 'phase2', 'function': 'acetylation'},
            'SULT1A1': {'phase': 'phase2', 'function': 'sulfation'},
            'ABCB1': {'phase': 'phase3', 'function': 'efflux_transport'},
            'ABCC2': {'phase': 'phase3', 'function': 'efflux_transport'},
            'SLCO1B1': {'phase': 'phase3', 'function': 'uptake_transport'}
        }
    
    def get_analyzer_name(self) -> str:
        return "detoxification"
    
    async def can_analyze(self, context: AnalysisContext) -> bool:
        """Check if variant affects detox genes."""
        gene = self.extract_gene_from_variant(context.analysis_variant)
        return gene is not None and gene in self.detox_genes
    
    async def analyze(self, context: AnalysisContext) -> Optional[DetoxificationProfile]:
        """Generate detoxification profile."""
        try:
            gene = self.extract_gene_from_variant(context.analysis_variant)
            if not gene or gene not in self.detox_genes:
                return None
            
            detox_info = self.detox_genes[gene]
            clinical_significance = self.extract_clinical_significance(context.annotation)
            detox_capacity = self._assess_detox_capacity(gene, clinical_significance)
            toxin_sensitivity = self._assess_toxin_sensitivity(detox_capacity)
            support_recommendations = self._generate_detox_support(gene, detox_capacity)
            
            profile = DetoxificationProfile(
                analysis_id=context.analysis_id,
                detox_phase=detox_info['phase'],
                gene=gene,
                detox_capacity=detox_capacity,
                toxin_sensitivity=toxin_sensitivity,
                support_recommendations=support_recommendations,
                associated_variants=[str(context.analysis_variant.rsid)]
            )
            
            context.session.add(profile)
            logger.info(f"Generated detox profile for {gene}")
            return profile
            
        except Exception as e:
            logger.error(f"Error generating detox profile for {context.analysis_variant.rsid}: {e}")
            return None
    
    def _assess_detox_capacity(self, gene: str, clinical_significance: str) -> str:
        """Assess detoxification capacity."""
        if gene in ['GSTM1', 'GSTT1']:
            if 'null' in clinical_significance.lower() or 'deletion' in clinical_significance.lower():
                return 'impaired'
        elif gene.startswith('CYP'):
            if 'poor metabolizer' in clinical_significance.lower():
                return 'slow'
            elif 'ultra-rapid metabolizer' in clinical_significance.lower():
                return 'fast'
            elif 'extensive metabolizer' in clinical_significance.lower():
                return 'normal'
            else:
                return 'intermediate'
        
        return 'normal'
    
    def _assess_toxin_sensitivity(self, capacity: str) -> str:
        """Assess toxin sensitivity."""
        if capacity in ['impaired', 'slow']:
            return 'high'
        elif capacity == 'fast':
            return 'low'
        else:
            return 'moderate'
    
    def _generate_detox_support(self, gene: str, capacity: str) -> List[str]:
        """Generate detox support recommendations."""
        recommendations = []
        
        if capacity in ['impaired', 'slow']:
            recommendations.extend([
                'Consider additional antioxidant support',
                'Reduce exposure to environmental toxins',
                'Support liver function with milk thistle'
            ])
        
        if gene in ['GSTM1', 'GSTT1']:
            recommendations.extend([
                'Increase cruciferous vegetables',
                'Consider glutathione supplementation',
                'NAC (N-acetylcysteine) support'
            ])
        elif gene.startswith('CYP'):
            recommendations.extend([
                'Be cautious with medication dosing',
                'Consider genetic counseling for drug therapy',
                'Monitor for drug interactions'
            ])
        
        return recommendations


class SportsPerformanceAnalyzer(BaseAnalyzer):
    """Analyzes sports and fitness-related genetic variants."""
    
    def __init__(self):
        super().__init__()
        self.sports_genes = {
            'ACTN3': {
                'category': 'muscle_fiber_type',
                'variants': ['rs1815739'],
                'performance_aspects': ['power', 'sprint_performance']
            },
            'ACE': {
                'category': 'endurance',
                'variants': ['rs4341'],
                'performance_aspects': ['aerobic_capacity', 'endurance']
            },
            'CKM': {
                'category': 'recovery',
                'variants': ['rs8111989'],
                'performance_aspects': ['muscle_recovery', 'energy_metabolism']
            },
            'COL1A1': {
                'category': 'injury_resistance',
                'variants': ['rs1800012'],
                'performance_aspects': ['connective_tissue', 'injury_prevention']
            },
            'PPARA': {
                'category': 'fat_metabolism',
                'variants': ['rs4253778'],
                'performance_aspects': ['fat_burning', 'endurance']
            }
        }
    
    def get_analyzer_name(self) -> str:
        return "sports_performance"
    
    async def can_analyze(self, context: AnalysisContext) -> bool:
        """Check if variant affects sports performance."""
        rsid = str(context.analysis_variant.rsid)
        
        for gene, gene_info in self.sports_genes.items():
            if self.is_rsid_in_variant_list(rsid, gene_info['variants']):
                return True
        
        return False
    
    async def analyze(self, context: AnalysisContext) -> Optional[SportsPerformance]:
        """Generate sports performance profile."""
        try:
            rsid = str(context.analysis_variant.rsid)
            affected_gene = None
            
            for gene, gene_info in self.sports_genes.items():
                if self.is_rsid_in_variant_list(rsid, gene_info['variants']):
                    affected_gene = gene
                    break
            
            if not affected_gene:
                return None
            
            gene_info = self.sports_genes[affected_gene]
            clinical_significance = self.extract_clinical_significance(context.annotation)
            genetic_advantage = self._assess_genetic_advantage(affected_gene, rsid, clinical_significance)
            sport_recommendations = self._generate_sport_recommendations(affected_gene, genetic_advantage)
            training_advice = self._generate_training_advice(affected_gene, genetic_advantage)
            
            profile = SportsPerformance(
                analysis_id=context.analysis_id,
                performance_category=gene_info['category'],
                genetic_advantage=genetic_advantage,
                sport_recommendations=sport_recommendations,
                associated_variants=[rsid],
                training_advice=training_advice
            )
            
            context.session.add(profile)
            logger.info(f"Generated sports performance profile for {affected_gene}")
            return profile
            
        except Exception as e:
            logger.error(f"Error generating sports performance profile for {context.analysis_variant.rsid}: {e}")
            return None
    
    def _assess_genetic_advantage(self, gene: str, rsid: str, clinical_significance: str) -> str:
        """Assess genetic advantage for sports performance."""
        if gene == 'ACTN3':
            if 'XX' in clinical_significance or 'null' in clinical_significance.lower():
                return 'moderate'  # Better for endurance
            else:
                return 'high'  # Better for power
        elif gene == 'ACE':
            if 'I/I' in clinical_significance:
                return 'high'  # Better for endurance
            elif 'D/D' in clinical_significance:
                return 'moderate'  # Better for power
            else:
                return 'moderate'
        
        return 'moderate'
    
    def _generate_sport_recommendations(self, gene: str, advantage: str) -> List[str]:
        """Generate sport recommendations."""
        recommendations = []
        
        if gene == 'ACTN3':
            if advantage == 'high':
                recommendations.extend(['Power sports', 'Sprinting', 'Weightlifting', 'Rugby'])
            else:
                recommendations.extend(['Endurance sports', 'Marathon running', 'Cycling', 'Swimming'])
        elif gene == 'ACE':
            if advantage == 'high':
                recommendations.extend(['Distance running', 'Cycling', 'Triathlon', 'Cross-country skiing'])
            else:
                recommendations.extend(['Powerlifting', 'Shot put', 'Boxing', 'Wrestling'])
        elif gene == 'CKM':
            recommendations.extend(['Mixed training', 'CrossFit', 'Martial arts', 'Team sports'])
        
        return recommendations
    
    def _generate_training_advice(self, gene: str, advantage: str) -> str:
        """Generate training advice."""
        if gene == 'ACTN3':
            if advantage == 'high':
                return "Focus on power and strength training with explosive movements. Emphasize sprints and plyometrics."
            else:
                return "Optimize for endurance training with longer duration activities. Focus on aerobic capacity building."
        elif gene == 'ACE':
            if advantage == 'high':
                return "Prioritize endurance training with steady-state cardio and longer training sessions."
            else:
                return "Focus on power and strength development with shorter, high-intensity training sessions."
        
        return "Balanced training approach with both power and endurance components."


class SpecializedAnalyzerManager:
    """Manages all specialized genetic analyzers."""
    
    def __init__(self):
        # Register all analyzers
        analyzer_registry.register(MethylationAnalyzer())
        analyzer_registry.register(DetoxificationAnalyzer())
        analyzer_registry.register(SportsPerformanceAnalyzer())
        # Add more analyzers as needed
    
    async def generate_all_specialized_profiles(
        self,
        variant,
        annotation: Dict[str, Any],
        analysis_id: int,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """Generate all applicable specialized profiles for a variant."""
        context = AnalysisContext(
            analysis_id=analysis_id,
            analysis_variant=variant,
            annotation=annotation,
            session=session
        )
        
        results = await analyzer_registry.analyze_all(context)
        
        # Commit all changes at once
        try:
            await session.commit()
            logger.info(f"Successfully saved specialized profiles for {variant.rsid}")
        except Exception as e:
            logger.error(f"Error saving specialized profiles for {variant.rsid}: {e}")
            await session.rollback()
            results['save_error'] = str(e)
        
        return results


# Alias for backward compatibility
SpecializedAnalyzerService = SpecializedAnalyzerManager