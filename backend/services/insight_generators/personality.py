"""Personality trait insight generator."""
from ...db.models import PersonalityTrait
from .base import GeneratorContext, generate_from_maps, zygosity_adjust, boost_if_pathogenic


async def generate_personality_traits(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        adjusted = zygosity_adjust(info['tendency'], genotype, ref_allele=info.get('_ref_allele'))
        return PersonalityTrait(
            analysis_id=aid, trait_name=info['trait'],
            genetic_tendency=boost_if_pathogenic(adjusted, info.get('_pathogenicity_score')),
            confidence_level=info['confidence'],
            associated_variants=[rsid],
            behavioral_insights=info['insights']
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        adjusted = zygosity_adjust(info['tendency'], genotype, ref_allele=ref_allele) if genotype else info['tendency']
        return PersonalityTrait(
            analysis_id=aid, trait_name=info['trait'],
            genetic_tendency=boost_if_pathogenic(adjusted, info.get('_pathogenicity_score')),
            confidence_level=info['confidence'],
            associated_variants=[rsid],
            behavioral_insights=info['insights']
        )

    rsid_map, gene_map = ctx.get_maps('personality')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='trait',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
