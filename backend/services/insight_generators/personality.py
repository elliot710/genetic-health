"""Personality trait insight generator."""
from ...db.models import PersonalityTrait
from .base import GeneratorContext, generate_from_maps


async def generate_personality_traits(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        return PersonalityTrait(
            analysis_id=aid, trait_name=info['trait'],
            genetic_tendency=info['tendency'], confidence_level=info['confidence'],
            associated_variants=[rsid],
            behavioral_insights=info['insights']
        )

    def from_gene(aid, rsid, gene, consequence, info):
        return PersonalityTrait(
            analysis_id=aid, trait_name=info['trait'],
            genetic_tendency=info['tendency'], confidence_level=info['confidence'],
            associated_variants=[rsid],
            behavioral_insights=info['insights']
        )

    rsid_map, gene_map = ctx.get_maps('personality')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='trait',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
