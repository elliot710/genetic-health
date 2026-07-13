import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.shared_annotation_service import (
    _row_to_annotation_dict,
    _empty_annotation_dict,
    _ANNOTATION_COL_MAP,
    SharedVariantAnnotationService,
)


class TestRowToAnnotationDict:
    def _make_row(self, **overrides):
        base = [None] * (1 + len(_ANNOTATION_COL_MAP))
        base[0] = "rs123"
        for i, (_, key) in enumerate(_ANNOTATION_COL_MAP, start=1):
            if key in overrides:
                base[i] = overrides[key]
        return base

    def test_empty_row_returns_zero_success_count(self):
        row = self._make_row()
        result = _row_to_annotation_dict(row)
        assert result["rsid"] == "rs123"
        assert result["success_count"] == 0
        assert result["annotations"] == {}
        assert result["sources_queried"] == []

    def test_populated_columns_are_mapped(self):
        data = {"found": True, "score": 0.9}
        row = self._make_row(ensembl=data, gnomad={"found": True})
        result = _row_to_annotation_dict(row)
        assert result["annotations"]["ensembl"] == data
        assert result["annotations"]["gnomad"] == {"found": True}
        assert result["success_count"] == 2
        assert set(result["sources_queried"]) == {"ensembl", "gnomad"}

    def test_none_columns_are_excluded(self):
        row = self._make_row(clinvar={"found": True})
        result = _row_to_annotation_dict(row)
        assert "ensembl" not in result["annotations"]
        assert "clinvar" in result["annotations"]


class TestEmptyAnnotationDict:
    def test_structure(self):
        result = _empty_annotation_dict("rs999")
        assert result == {
            "rsid": "rs999",
            "annotations": {},
            "sources_queried": [],
            "success_count": 0,
        }


class TestGetExistingAnnotations:
    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_input(self):
        svc = SharedVariantAnnotationService()
        result = await svc.get_existing_annotations([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_only_non_empty_rows(self):
        svc = SharedVariantAnnotationService()

        empty_row = [None] * (1 + len(_ANNOTATION_COL_MAP))
        empty_row[0] = "rs000"
        populated_row = [None] * (1 + len(_ANNOTATION_COL_MAP))
        populated_row[0] = "rs111"
        populated_row[1] = {"found": True}

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [empty_row, populated_row]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.db.database.async_session_factory", return_value=mock_session), \
             patch.object(svc, '_increment_usage_counts', AsyncMock()):
            result = await svc.get_existing_annotations(["rs000", "rs111"])

        assert "rs000" not in result
        assert "rs111" in result
        assert result["rs111"]["success_count"] == 1
