"""
Insight generators — each module generates one category of insights
from annotated variant data.

All generators follow the same signature:
    async def generate(ctx: GeneratorContext) -> int

Returns the number of insight rows created.
"""
from .base import GeneratorContext, extract_gene_and_consequence, extract_frequency, zygosity_adjust
from .health import generate_health_risks
from .drug_response import generate_drug_responses
from .physical_traits import generate_physical_traits
from .nutrition import generate_nutrition_traits
from .sports import generate_sports_performance
from .cognitive import generate_cognitive_profiles
from .personality import generate_personality_traits
from .ancestry import generate_ancestry_results
from .carrier import generate_carrier_status
from .wellness import generate_wellness_metrics
from .methylation import generate_methylation_profiles
from .detox import generate_detox_profiles
from .rare_mutations import generate_rare_mutations
from .uncommon_mutations import generate_uncommon_mutations

ALL_GENERATORS = [
    ('health_risks', generate_health_risks),
    ('drug_responses', generate_drug_responses),
    ('physical_traits', generate_physical_traits),
    ('nutrition_traits', generate_nutrition_traits),
    ('sports_performance', generate_sports_performance),
    ('cognitive_profiles', generate_cognitive_profiles),
    ('personality_traits', generate_personality_traits),
    ('ancestry_results', generate_ancestry_results),
    ('carrier_status', generate_carrier_status),
    ('wellness_metrics', generate_wellness_metrics),
    ('methylation_profiles', generate_methylation_profiles),
    ('detox_profiles', generate_detox_profiles),
    ('rare_mutations', generate_rare_mutations),
    ('uncommon_mutations', generate_uncommon_mutations),
]

__all__ = [
    'GeneratorContext',
    'ALL_GENERATORS',
    'extract_gene_and_consequence',
    'extract_frequency',
    'generate_health_risks',
    'generate_drug_responses',
    'generate_physical_traits',
    'generate_nutrition_traits',
    'generate_sports_performance',
    'generate_cognitive_profiles',
    'generate_personality_traits',
    'generate_ancestry_results',
    'generate_carrier_status',
    'generate_wellness_metrics',
    'generate_methylation_profiles',
    'generate_detox_profiles',
    'generate_rare_mutations',
    'generate_uncommon_mutations',
]
