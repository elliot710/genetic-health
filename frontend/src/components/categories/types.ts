import { LucideIcon } from 'lucide-react'

// ─── Gene-level ClinVar statistics ────────────────────────────

export interface GeneCondition {
  disease_name: string
  disease_mim?: string | null
  source_id?: string | null
}

export interface GeneStats {
  pathogenic_lp: number         // Pathogenic + Likely Pathogenic submissions
  vus: number                   // Variants of Uncertain Significance
  total_submissions: number     // Total ClinVar submissions for this gene
  total_alleles: number
  with_conflicts: number
  gene_mim?: string | null      // OMIM gene number
  conditions: GeneCondition[]   // Known disease associations
}

// ─── API Response Types ────────────────────────────────────────

export interface HealthRisk {
  condition: string
  risk_level: string
  risk_score: string
  associated_variants: string[]
  recommendations: string[]
  clinical_significance?: string
  gene?: string
  review_status?: string
  pathogenicity_classification?: string
}

export interface DrugResponse {
  gene: string
  drug: string
  response_type: string
  recommendations: string
  variants_involved: string[]
}

export interface Haplogroup {
  haplogroup: string
  origin?: string
  frequency?: string
  age?: string
  description?: string
  migration_path?: string
}

export interface NeanderthalData {
  percentage: number
  variants: number
  moreOrLess: string
  comparison: string
}

export interface AncestryResult {
  population: string
  percentage: string
  confidence: string
  geographic_origin: string
  composition?: Array<{ region: string; percentage: number; color?: string }>
  maternal_haplogroup?: Haplogroup
  paternal_haplogroup?: Haplogroup
  neanderthal_variants?: NeanderthalData
}

export interface SportsPerformance {
  category: string
  genetic_advantage: string
  sport_recommendations: string[]
  training_advice: string
  performance_category?: string
  trait_name?: string
  associated_variants?: string[]
  genetic_result?: string
  description?: string
}

export interface NutritionTrait {
  nutrient: string
  metabolism_type: string
  dietary_recommendations: string[]
  sensitivity_level: string
  trait_name?: string
  associated_variants?: string[]
  description?: string
  genetic_result?: string
}

export interface CarrierCondition {
  condition: string
  gene: string
  status: string
  inheritance: string
  associated_variants: string[]
  description: string
  carrier_status?: string
  inheritance_pattern?: string
  population_frequency?: string
  risk_level?: string
  genetic_counseling_recommended?: boolean
}

export interface MethylationProfile {
  gene: string
  variant: string
  methylation_capacity: string
  supplement_recommendations: string[]
  associated_variants: string[]
}

export interface DetoxProfile {
  detox_phase: string
  gene: string
  detox_capacity: string
  toxin_sensitivity: string
  support_recommendations: string[]
  associated_variants: string[]
}

export interface RareMutation {
  gene: string
  mutation_type: string
  mutation_name: string
  clinical_significance: string
  disease_association: string
  penetrance: string
  population_frequency: number
  associated_variants: string[]
  rsid?: string
  effect?: string
  family_screening_recommended?: boolean
  genetic_counseling_urgent?: boolean
  medical_follow_up?: string
  literature_support?: string
  variant_id?: string
  chromosome?: string
  position?: number
  ref_allele?: string
  alt_allele?: string
  inheritance_pattern?: string
  clinical_actions?: string[]
  monitoring_recommendations?: string[]
  specialist_referral?: string
  genotype?: string
}

export interface MetabolicMetric {
  metric_name: string
  genetic_predisposition: string
  optimization_score: string
  lifestyle_recommendations: string[]
}

export interface WellnessTrait {
  trait: string
  category: string
  value: string
  gene: string
  confidence: string
  name: string
  result: string
  marker: string
  recommendations: string[]
}

export interface PhysicalTrait {
  trait_name: string
  trait_category: string
  genetic_result: string
  confidence: string
  associated_variants: string[]
  description: string
  category: string
  trait_value?: string
  result?: string
  associated_gene?: string
}

export interface IntelligenceTrait {
  cognitive_ability: string
  trait_name: string
  genetic_advantage: string
  genetic_result: string
  percentile: number
  associated_variants: string[]
  description: string
  enhancement_suggestions: string[]
}

export interface PersonalityTraitData {
  trait: string
  name: string
  score: number
  confidence: string
  gene: string
  marker: string
  description: string
  summary: string
  characteristics: string[]
}

export interface UncommonMutation {
  rsid: string
  gene: string
  effect: string
  population_frequency: number
  effect_size: string
  research_status: string
  clinical_relevance: string
  literature_count: number
  mutation_name: string
  mutation_type: string
}

export interface DashboardData {
  summary?: {
    total_variants: number
    processed_variants?: number
    analyzed_variants?: number
    insights_found?: number
    analysis_id: number
    status?: string
    upload_date?: string
    filename?: string
    upload_info?: { filename?: string; [key: string]: unknown }
    data_sources?: string[]
    [key: string]: unknown
  }
  health_risks?: HealthRisk[] | { details?: HealthRisk[] }
  drug_responses?: DrugResponse[] | { details?: DrugResponse[] }
  drug_interactions?: {
    details?: DrugResponse[]
    high_risk_genes?: string[]
    moderate_risk_genes?: string[]
    affected_drug_classes?: string[]
  }
  ancestry_results?: AncestryResult[]
  sports_performance?: SportsPerformance[]
  nutrition_traits?: NutritionTrait[]
  carrier_status?: CarrierCondition[]
  methylation_profiles?: MethylationProfile[]
  detoxification_profiles?: DetoxProfile[]
  rare_mutations?: RareMutation[]
  metabolic?: { metrics: MetabolicMetric[] }
  wellness_traits?: WellnessTrait[]
  physical_traits?: PhysicalTrait[]
  intelligence?: IntelligenceTrait[]
  personality_traits?: PersonalityTraitData[]
  uncommon_mutations?: UncommonMutation[]
  alpha_missense_map?: Record<string, { score?: number; classification?: string }>
  clinvar_count_map?: Record<string, number>
  genotype_map?: Record<string, string>
  pathogenicity_map?: Record<string, { score: number; classification: string; confidence: string; evidence_count: number }>
  gene_stats_map?: Record<string, GeneStats>
  alphafold_map?: Record<string, { confidence: number; high_confidence_pct: number; low_confidence_pct: number; protein_name?: string }>
  pharmgkb_map?: Record<string, { gene: string; haplotypes?: string[]; cpic_guideline?: string; phenotype?: string; star_allele?: string }>
  real_data?: {
    variants?: { rsid?: string; chromosome?: string; position?: number; genotype?: string }[]
    analysis?: Record<string, unknown>
    upload_result?: { filename?: string; [key: string]: unknown }
  }
}

// ─── Common Panel Props ────────────────────────────────────────

export interface CategoryPanelProps {
  isDarkMode?: boolean
  data?: DashboardData
  token?: string
}

// ─── UI Helper Types ───────────────────────────────────────────

export interface CategoryIconConfig {
  icon: LucideIcon
  color: string
  bgColor: string
}
