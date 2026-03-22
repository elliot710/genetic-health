"""Physical traits insight generator."""
from ...db.models import PhysicalTrait
from .base import GeneratorContext, generate_from_maps, get_trait_description, zygosity_adjust


async def generate_physical_traits(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        return PhysicalTrait(
            analysis_id=aid, trait_name=info['trait'],
            trait_category=info['category'],
            genetic_result=info['result'],
            confidence=zygosity_adjust(info['confidence'], genotype, ref_allele=info.get('_ref_allele')),
            associated_variants=[rsid],
            description=get_trait_description(info['trait'], info['result'])
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        confidence = 'high' if consequence in ('missense_variant', 'stop_gained', 'frameshift_variant') else info['confidence']
        confidence = zygosity_adjust(confidence, genotype, ref_allele=ref_allele) if genotype else confidence
        return PhysicalTrait(
            analysis_id=aid, trait_name=info['trait'],
            trait_category=info['category'], genetic_result=info['result'],
            confidence=confidence, associated_variants=[rsid],
            description=info['description']
        )

    rsid_map, gene_map = ctx.get_maps('physical')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='trait',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
