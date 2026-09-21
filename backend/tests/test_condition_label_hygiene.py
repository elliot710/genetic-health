"""What a rare-mutation card is allowed to call a condition.

Two failure modes seen live: a ClinVar record with no curated condition puts
the gene symbol in the condition field, so the card reads "Pold2" as though it
were a diagnosis; and pharmacogenomic entries like "Tramadol response" surface
on the rare-disease panel, framing ordinary drug metabolism as a disorder.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.services.insight_generators.base import GeneratorContext, VariantProfile
from backend.services.insight_generators.rare_mutations import generate_rare_mutations

STRONG = ["criteria provided, multiple submitters, no conflicts"]
NO_ASSOCIATION = "No known disease association"


def _make_annotation(rsid, gene, conditions):
    annotation = MagicMock()
    annotation.rsid = rsid
    annotation.annotation_data = {
        "annotations": {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": conditions,
                "genes": [gene],
                "ref_allele": "C",
                "alt_allele": "T",
                "review_statuses": STRONG,
            },
            "ensembl": {},
        }
    }
    return annotation


def _emit(gene, conditions, rsid="rs1000"):
    variant = SimpleNamespace(rsid=rsid, chromosome="1", genotype="TT")
    annotation = _make_annotation(rsid, gene, conditions)
    profile = VariantProfile(
        rsid=rsid, genotype="TT", effective_ref=None, gene=gene,
        consequence="missense_variant", impact="HIGH", chromosome="1",
        population_frequency=1.2e-5, clinical_significance="pathogenic",
        is_benign=False, is_hom_ref=False, is_het=False, is_no_call=False,
        composite_score=0.95, pathogenicity_score=None,
        annotation_result=annotation, variant=None,
    )
    session = AsyncMock()
    added = []
    session.add = MagicMock(side_effect=lambda obj: added.append(obj))
    ctx = GeneratorContext(
        analysis_id=1, variants=[variant], annotation_results={rsid: annotation},
        session=session, rsid_gene_map={}, registry={},
        variant_profiles={rsid: profile}, inferred_sex=None,
    )
    asyncio.new_event_loop().run_until_complete(generate_rare_mutations(ctx))
    return added


class TestBareGeneSymbolIsNotADiagnosis:
    def test_condition_equal_to_its_gene_symbol_is_dropped(self):
        added = _emit("POLD2", ["Pold2"])
        assert added[0].disease_association == NO_ASSOCIATION

    def test_matching_ignores_case(self):
        added = _emit("CYP2C19", ["Cyp2c19"])
        assert added[0].disease_association == NO_ASSOCIATION

    def test_a_real_condition_alongside_the_symbol_survives(self):
        added = _emit("MECP2", ["Mecp2", "Rett syndrome"])
        assert added[0].disease_association == "Rett syndrome"

    def test_a_real_disease_name_is_retained(self):
        added = _emit("MECP2", ["Rett syndrome"])
        assert added[0].disease_association == "Rett syndrome"


class TestPharmacogenomicEntriesBelongToDrugResponses:
    def test_drug_response_only_variant_is_absent_from_rare_mutations(self):
        assert _emit("CYP2D6", ["Tramadol response"]) == []

    def test_metabolizer_finding_is_absent_from_rare_mutations(self):
        assert _emit("CYP2C19", ["CYP2C19 poor metabolizer"]) == []

    def test_a_variant_with_a_real_disease_too_is_still_reported(self):
        added = _emit("CYP2C19", ["Tramadol response", "Some real syndrome"])
        assert added[0].disease_association == "Some real syndrome"


class TestDiseaseNamesEndingInResponse:
    """Scanning the real ClinVar corpus, a bare "ends with response" rule also
    caught a genuine inherited retinal disease. Over-suppression hides a true
    finding, which is the failure mode this whole change exists to avoid."""

    def test_a_retinal_dystrophy_is_not_mistaken_for_a_drug_entry(self):
        added = _emit("KCNV2", ["Cone dystrophy with supernormal rod response"])
        assert added[0].disease_association == "Cone dystrophy with supernormal rod response"

    def test_a_real_drug_response_entry_is_still_suppressed(self):
        assert _emit("CYP2C9", ["Warfarin response"]) == []

    def test_a_disease_noun_anywhere_in_the_name_protects_it(self):
        added = _emit("ABCA4", ["Retinitis pigmentosa with paradoxical response"])
        assert added[0].disease_association == "Retinitis pigmentosa with paradoxical response"
