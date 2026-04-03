"""Tests for pure helper functions in variant_loader.py."""
import asyncio
from unittest.mock import patch

import pytest


class TestFindGeneAtPosition:
    """Tests for _find_gene_at_position — binary search over gene coordinates."""

    def _load(self):
        from backend.services.variant_loader import _find_gene_at_position
        return _find_gene_at_position

    def _make_table(self, entries):
        table = {}
        for chrom, start, end, symbol, biotype in entries:
            table.setdefault(chrom, []).append((start, end, symbol, biotype))
        for chrom in table:
            table[chrom].sort()
        return table

    def test_returns_none_for_unknown_chrom(self):
        fn = self._load()
        result = fn({}, "1", 1000)
        assert result is None

    def test_returns_none_when_no_genes_on_chrom(self):
        fn = self._load()
        result = fn({"1": []}, "1", 1000)
        assert result is None

    def test_returns_gene_when_pos_overlaps(self):
        fn = self._load()
        table = self._make_table([("1", 100, 200, "GENE1", "protein_coding")])
        assert fn(table, "1", 150) == "GENE1"

    def test_returns_none_when_pos_before_all_genes(self):
        fn = self._load()
        table = self._make_table([("1", 500, 1000, "GENE1", "protein_coding")])
        assert fn(table, "1", 50) is None

    def test_returns_none_when_pos_after_gene_end(self):
        fn = self._load()
        table = self._make_table([("1", 100, 200, "GENE1", "protein_coding")])
        assert fn(table, "1", 300) is None

    def test_prefers_protein_coding_over_other_biotype(self):
        fn = self._load()
        table = self._make_table([
            ("1", 100, 500, "NONCODING", "lincRNA"),
            ("1", 150, 300, "CODING", "protein_coding"),
        ])
        assert fn(table, "1", 200) == "CODING"

    def test_prefers_smaller_gene_among_same_biotype(self):
        fn = self._load()
        table = self._make_table([
            ("1", 100, 1000, "BIG_GENE", "protein_coding"),
            ("1", 150, 300, "SMALL_GENE", "protein_coding"),
        ])
        assert fn(table, "1", 200) == "SMALL_GENE"

    def test_handles_gene_at_exact_start_boundary(self):
        fn = self._load()
        table = self._make_table([("1", 100, 200, "GENE1", "protein_coding")])
        assert fn(table, "1", 100) == "GENE1"

    def test_handles_gene_at_exact_end_boundary(self):
        fn = self._load()
        table = self._make_table([("1", 100, 200, "GENE1", "protein_coding")])
        assert fn(table, "1", 200) == "GENE1"

    def test_stops_search_when_too_far_back(self):
        fn = self._load()
        table = self._make_table([
            ("1", 1, 100, "FAR_GENE", "protein_coding"),
            ("1", 3_000_000, 4_000_000, "MID_GENE", "protein_coding"),
        ])
        assert fn(table, "1", 3_500_000) == "MID_GENE"

    def test_multiple_chromosomes_returns_correct_one(self):
        fn = self._load()
        table = self._make_table([
            ("1", 100, 200, "GENE_CHR1", "protein_coding"),
            ("2", 100, 200, "GENE_CHR2", "protein_coding"),
        ])
        assert fn(table, "1", 150) == "GENE_CHR1"
        assert fn(table, "2", 150) == "GENE_CHR2"

    def test_non_coding_returned_when_no_coding_overlaps(self):
        fn = self._load()
        table = self._make_table([("1", 100, 400, "NC_GENE", "pseudogene")])
        assert fn(table, "1", 200) == "NC_GENE"


class TestGetGeneCoordLock:
    """Tests for _get_gene_coord_lock singleton creation."""

    def test_returns_asyncio_lock(self):
        import backend.services.variant_loader as vl
        vl._GENE_COORD_LOCK = None
        lock = vl._get_gene_coord_lock()
        assert isinstance(lock, asyncio.Lock)

    def test_returns_same_instance_on_repeated_calls(self):
        import backend.services.variant_loader as vl
        vl._GENE_COORD_LOCK = None
        lock1 = vl._get_gene_coord_lock()
        lock2 = vl._get_gene_coord_lock()
        assert lock1 is lock2

    def test_reuses_existing_lock(self):
        import backend.services.variant_loader as vl
        existing = asyncio.Lock()
        vl._GENE_COORD_LOCK = existing
        assert vl._get_gene_coord_lock() is existing
