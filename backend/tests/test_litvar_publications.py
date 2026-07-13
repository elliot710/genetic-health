"""Proof that LitVar publication data reaches extract_publications as a list.

Bug: OptimizedGeneticAPIService._get_litvar_annotation only stored a PMID
*count* (total_publications), never the individual publications, so
variant_detail_builder.extract_publications always saw an empty list even
when LitVar had literature for the variant.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.genetic_api_service import APIResponse, OptimizedGeneticAPIService
from backend.services.variant_detail_builder import extract_publications


LITVAR_AUTOCOMPLETE_URL = "https://www.ncbi.nlm.nih.gov/research/litvar2-api/variant/autocomplete"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def _make_request_side_effect(endpoint_name, url, params=None, **kwargs):
    if url == LITVAR_AUTOCOMPLETE_URL:
        return APIResponse(success=True, data=[{
            "rsid": "rs1799990",
            "pmids_count": 2,
            "gene": ["PRNP"],
            "name": "p.M129V",
            "data_clinical_significance": ["pathogenic"],
        }])
    if url == ESEARCH_URL:
        return APIResponse(success=True, data={
            "esearchresult": {"idlist": ["111", "222"]}
        })
    if url == ESUMMARY_URL:
        return APIResponse(success=True, data={
            "result": {
                "uids": ["111", "222"],
                "111": {"title": "Study one", "fulljournalname": "Nature", "pubdate": "2020 Jan"},
                "222": {"title": "Study two", "fulljournalname": "Cell", "pubdate": "2021"},
            }
        })
    raise AssertionError(f"Unexpected request to {url}")


class TestGetLitvarAnnotationPublications:
    @pytest.mark.asyncio
    async def test_stores_non_empty_publications_list(self):
        with patch("backend.services.genetic_api_service.settings.api.max_concurrent", 3):
            service = OptimizedGeneticAPIService()
        with patch.object(service, "_make_request", AsyncMock(side_effect=_make_request_side_effect)):
            result = await service._get_litvar_annotation("rs1799990")

        assert result["found"] is True
        assert result["total_publications"] == 2
        publications = result["publications"]
        assert publications, "expected a non-empty publications list"
        assert publications[0]["pmid"] == "111"
        assert publications[0]["title"] == "Study one"
        assert publications[0]["journal"] == "Nature"
        assert publications[0]["year"] == 2020

    @pytest.mark.asyncio
    async def test_no_publications_when_pubmed_lookup_empty(self):
        with patch("backend.services.genetic_api_service.settings.api.max_concurrent", 3):
            service = OptimizedGeneticAPIService()

        def no_pmids(endpoint_name, url, params=None, **kwargs):
            if url == LITVAR_AUTOCOMPLETE_URL:
                return APIResponse(success=True, data=[{
                    "rsid": "rs1799990", "pmids_count": 2,
                }])
            if url == ESEARCH_URL:
                return APIResponse(success=True, data={"esearchresult": {"idlist": []}})
            raise AssertionError(f"Unexpected request to {url}")

        with patch.object(service, "_make_request", AsyncMock(side_effect=no_pmids)):
            result = await service._get_litvar_annotation("rs1799990")

        assert result["publications"] == []


class TestExtractPublicationsFromLitvarShape:
    def test_yields_non_empty_list_with_expected_keys(self):
        annotation = SimpleNamespace(litvar_data={
            "found": True,
            "source": "litvar",
            "total_publications": 1,
            "publications": [
                {"pmid": "111", "title": "Study one", "journal": "Nature", "year": 2020},
            ],
        })
        response = {}

        extract_publications(annotation, response)

        assert response["publications"]["count"] == 1
        assert response["publications"]["items"] == [
            {"pmid": "111", "title": "Study one", "journal": "Nature", "year": 2020},
        ]

    def test_no_publications_key_when_litvar_not_found(self):
        annotation = SimpleNamespace(litvar_data={"found": False, "source": "litvar"})
        response = {}

        extract_publications(annotation, response)

        assert "publications" not in response
