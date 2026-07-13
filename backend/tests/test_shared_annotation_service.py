import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

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


class TestComputeAnnotationStatus:
    def setup_method(self):
        self.svc = SharedVariantAnnotationService()

    def test_completed_when_all_sources_present(self):
        ann_data = {
            "sources_queried": ["ensembl", "clinvar"],
            "success_count": 2,
            "annotations": {"ensembl": {"found": True}, "clinvar": {"found": True}},
        }
        status, failed = self.svc._compute_annotation_status(ann_data)
        assert status == "completed"
        assert failed == []

    def test_partial_when_some_sources_missing(self):
        ann_data = {
            "sources_queried": ["ensembl", "clinvar"],
            "success_count": 1,
            "annotations": {"ensembl": {"found": True}},
        }
        status, failed = self.svc._compute_annotation_status(ann_data)
        assert status == "partial"
        assert "clinvar" in failed

    def test_failed_when_no_sources_populated(self):
        ann_data = {
            "sources_queried": ["ensembl", "clinvar"],
            "success_count": 0,
            "annotations": {},
        }
        status, failed = self.svc._compute_annotation_status(ann_data)
        assert status == "failed"
        assert set(failed) == {"ensembl", "clinvar"}

    def test_empty_annotation_data_defaults(self):
        status, failed = self.svc._compute_annotation_status({})
        assert status == "failed"
        assert set(failed) == {'ensembl', 'clinvar', 'clinpgx', 'snpedia'}


class TestSaveAnnotationSurfacesFailure:
    @pytest.mark.asyncio
    async def test_db_failure_is_logged_and_raised(self, caplog):
        svc = SharedVariantAnnotationService()
        with patch("backend.services.shared_annotation_service.insert"), \
             patch(
                 "backend.db.database.async_session_factory",
                 side_effect=RuntimeError("connection refused"),
             ):
            with caplog.at_level(logging.ERROR, logger="backend.services.shared_annotation_service"):
                with pytest.raises(RuntimeError, match="connection refused"):
                    await svc.save_annotation(
                        rsid="rs12345",
                        annotation_data={"annotations": {}, "sources_queried": [], "success_count": 0},
                        analysis_id=1,
                        analysis_variant_id=1,
                    )

        assert any("Failed to save annotation" in r.message for r in caplog.records)


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
