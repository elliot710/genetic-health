from unittest.mock import AsyncMock, patch

from backend.services.annotation_loader import (
    resolve_gene_symbol, _response_gene_symbol,
)


def _patch_marker(gene):
    return patch(
        "backend.services.annotation_loader._marker_gene_symbol",
        new=AsyncMock(return_value=gene),
    )


class TestResponseGeneSymbol:
    def test_prefers_vep_transcript_gene(self):
        response = {"transcripts": [{"gene_symbol": "TP53"}]}
        assert _response_gene_symbol(response) == "TP53"

    def test_falls_back_to_clinvar_local_gene(self):
        response = {"transcripts": [], "clinvar_local": {"genes": ["MLH1"]}}
        assert _response_gene_symbol(response) == "MLH1"

    def test_falls_back_to_gnomad_gene(self):
        response = {"gnomad": {"gene": "APOE"}}
        assert _response_gene_symbol(response) == "APOE"

    def test_falls_back_to_gnomad_tx_gene(self):
        response = {"gnomad_tx": {"gene": "CFTR"}}
        assert _response_gene_symbol(response) == "CFTR"

    def test_returns_none_when_no_source_has_gene(self):
        assert _response_gene_symbol({"gnomad": {"found": False}}) is None


class TestResolveGeneSymbol:
    async def test_marker_gene_takes_priority_over_response(self):
        response = {"transcripts": [{"gene_symbol": "TP53"}]}
        with _patch_marker("BRCA1"):
            assert await resolve_gene_symbol("rs123", response, AsyncMock()) == "BRCA1"

    async def test_falls_back_to_response_when_marker_missing(self):
        response = {"transcripts": [{"gene_symbol": "TP53"}]}
        with _patch_marker(None):
            assert await resolve_gene_symbol("rs123", response, AsyncMock()) == "TP53"
