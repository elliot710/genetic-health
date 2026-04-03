"""Tests for datasource_utils.py pure functions."""
import json
import sqlite3
import tempfile
from pathlib import Path
import pytest
from backend.services.datasource_utils import (
    safe_float,
    safe_int,
    clean_str,
    parse_vcf_info,
    interpret_cadd,
    get_file_fingerprint,
    get_multi_file_fingerprint,
    is_cache_valid,
    save_cache_meta,
    open_cache_db,
    create_cache_db,
    finalize_cache_db,
    scan_data_source_availability,
)


class TestSafeFloat:
    def test_float_input(self):
        assert safe_float(1.5) == pytest.approx(1.5)

    def test_int_input(self):
        assert safe_float(5) == pytest.approx(5.0)

    def test_string_float(self):
        assert safe_float("3.14") == pytest.approx(3.14)

    def test_none_returns_none(self):
        assert safe_float(None) is None

    def test_invalid_string_returns_none(self):
        assert safe_float("not_a_number") is None

    def test_nan_returns_none(self):
        import math
        assert safe_float(float("nan")) is None

    def test_zero(self):
        assert safe_float(0) == pytest.approx(0.0)


class TestSafeInt:
    def test_int_input(self):
        assert safe_int(5) == 5

    def test_string_int(self):
        assert safe_int("10") == 10

    def test_float_converted(self):
        assert safe_int(3.7) == 3

    def test_none_returns_none(self):
        assert safe_int(None) is None

    def test_invalid_string_returns_none(self):
        assert safe_int("abc") is None


class TestCleanStr:
    def test_valid_string(self):
        assert clean_str("hello") == "hello"

    def test_strips_whitespace(self):
        assert clean_str("  hello  ") == "hello"

    def test_none_returns_none(self):
        assert clean_str(None) is None

    def test_dot_returns_none(self):
        assert clean_str(".") is None

    def test_na_returns_none(self):
        assert clean_str("NA") is None

    def test_nan_returns_none(self):
        assert clean_str("nan") is None

    def test_empty_string_returns_none(self):
        assert clean_str("") is None

    def test_dash_returns_none(self):
        assert clean_str("-") is None

    def test_n_slash_a_returns_none(self):
        assert clean_str("N/A") is None


class TestParseVcfInfo:
    def test_key_value_pair(self):
        result = parse_vcf_info("AF=0.05")
        assert result["AF"] == "0.05"

    def test_flag_field_gets_one(self):
        result = parse_vcf_info("SOMATIC")
        assert result["SOMATIC"] == "1"

    def test_multiple_pairs(self):
        result = parse_vcf_info("AC=2;AN=100;AF=0.02")
        assert result["AC"] == "2"
        assert result["AN"] == "100"
        assert result["AF"] == "0.02"

    def test_mixed_flags_and_values(self):
        result = parse_vcf_info("PASS;AC=3;DBSNP")
        assert result["PASS"] == "1"
        assert result["AC"] == "3"
        assert result["DBSNP"] == "1"

    def test_empty_string(self):
        result = parse_vcf_info("")
        assert result == {}

    def test_value_with_equals(self):
        result = parse_vcf_info("CSQ=A|B=C")
        assert result["CSQ"] == "A|B=C"


class TestInterpretCadd:
    def test_none_returns_none(self):
        assert interpret_cadd(None) is None

    def test_very_high_30_plus(self):
        result = interpret_cadd(30)
        assert "top 0.1%" in result

    def test_high_20_to_30(self):
        result = interpret_cadd(25)
        assert "top 1%" in result

    def test_moderate_15_to_20(self):
        result = interpret_cadd(17)
        assert "top ~3%" in result

    def test_low_10_to_15(self):
        result = interpret_cadd(12)
        assert "top ~10%" in result

    def test_benign_below_10(self):
        result = interpret_cadd(5)
        assert "Likely benign" in result

    def test_exactly_30(self):
        result = interpret_cadd(30)
        assert "0.1%" in result


class TestGetFileFingerprint:
    def test_returns_name_size(self, tmp_path):
        f = tmp_path / "test.vcf.gz"
        f.write_bytes(b"hello world")
        fp = get_file_fingerprint(f)
        assert "test.vcf.gz" in fp
        assert str(len(b"hello world")) in fp

    def test_missing_file_returns_name(self, tmp_path):
        f = tmp_path / "missing.vcf.gz"
        fp = get_file_fingerprint(f)
        assert "missing.vcf.gz" in fp


class TestGetMultiFileFingerprint:
    def test_returns_md5_string(self, tmp_path):
        f1 = tmp_path / "a.vcf.gz"
        f2 = tmp_path / "b.vcf.gz"
        f1.write_bytes(b"data1")
        f2.write_bytes(b"data2")
        fp = get_multi_file_fingerprint([f1, f2])
        assert len(fp) == 32  # MD5 hex

    def test_different_files_different_fp(self, tmp_path):
        f1 = tmp_path / "a.vcf.gz"
        f2 = tmp_path / "b.vcf.gz"
        f1.write_bytes(b"data1")
        f2.write_bytes(b"data2data2")
        fp1 = get_multi_file_fingerprint([f1])
        fp2 = get_multi_file_fingerprint([f2])
        assert fp1 != fp2


class TestIsCacheValid:
    def test_missing_sqlite_returns_false(self, tmp_path):
        sqlite = tmp_path / "cache.db"
        meta = tmp_path / "cache.meta.json"
        meta.write_text(json.dumps({"marker_fingerprint": "x", "file_fingerprint": "y"}))
        assert is_cache_valid(sqlite, meta, "x", "y") is False

    def test_missing_meta_returns_false(self, tmp_path):
        sqlite = tmp_path / "cache.db"
        sqlite.write_bytes(b"")
        meta = tmp_path / "cache.meta.json"
        assert is_cache_valid(sqlite, meta, "x", "y") is False

    def test_matching_fingerprints_returns_true(self, tmp_path):
        sqlite = tmp_path / "cache.db"
        meta = tmp_path / "cache.meta.json"
        sqlite.write_bytes(b"")
        meta.write_text(json.dumps({"marker_fingerprint": "abc", "file_fingerprint": "def"}))
        assert is_cache_valid(sqlite, meta, "abc", "def") is True

    def test_mismatched_fingerprints_returns_false(self, tmp_path):
        sqlite = tmp_path / "cache.db"
        meta = tmp_path / "cache.meta.json"
        sqlite.write_bytes(b"")
        meta.write_text(json.dumps({"marker_fingerprint": "abc", "file_fingerprint": "xxx"}))
        assert is_cache_valid(sqlite, meta, "abc", "def") is False

    def test_corrupt_meta_returns_false(self, tmp_path):
        sqlite = tmp_path / "cache.db"
        meta = tmp_path / "cache.meta.json"
        sqlite.write_bytes(b"")
        meta.write_bytes(b"not valid json")
        assert is_cache_valid(sqlite, meta, "abc", "def") is False


class TestSaveCacheMeta:
    def test_saves_valid_json(self, tmp_path):
        meta = tmp_path / "cache.meta.json"
        save_cache_meta(meta, "fp_markers", "fp_file", 1000)
        data = json.loads(meta.read_text())
        assert data["marker_fingerprint"] == "fp_markers"
        assert data["file_fingerprint"] == "fp_file"
        assert data["variant_count"] == 1000

    def test_creates_parent_dirs(self, tmp_path):
        meta = tmp_path / "nested" / "deep" / "cache.meta.json"
        save_cache_meta(meta, "fp", "fp2", 5)
        assert meta.exists()

    def test_extra_fields_included(self, tmp_path):
        meta = tmp_path / "meta.json"
        save_cache_meta(meta, "fp", "fp2", 5, extra={"custom": "value"})
        data = json.loads(meta.read_text())
        assert data["custom"] == "value"


class TestOpenCacheDb:
    def test_opens_connection(self, tmp_path):
        path = tmp_path / "cache.db"
        conn = open_cache_db(path)
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_wal_mode_set(self, tmp_path):
        path = tmp_path / "cache.db"
        conn = open_cache_db(path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"
        conn.close()


class TestCreateAndFinalizeCacheDb:
    def test_creates_temp_db(self, tmp_path):
        path = tmp_path / "cache.db"
        ddl = "CREATE TABLE variants (id INTEGER PRIMARY KEY, rsid TEXT)"
        conn = create_cache_db(path, ddl)
        assert conn is not None
        conn.execute("INSERT INTO variants (rsid) VALUES ('rs12345')")
        conn.commit()
        tmp = path.with_suffix(".tmp")
        finalize_cache_db(conn, tmp, path)
        assert path.exists()
        assert not tmp.exists()


class TestScanDataSourceAvailability:
    def test_returns_dict_for_known_sources(self, tmp_path):
        result = scan_data_source_availability(base_dir=tmp_path)
        assert "clinvar" in result
        assert "gnomad" in result
        assert "alpha_missense" in result

    def test_nonexistent_dir_marked_not_exists(self, tmp_path):
        result = scan_data_source_availability(base_dir=tmp_path / "no_such_dir")
        assert result["clinvar"]["exists"] is False

    def test_empty_dir_zero_files(self, tmp_path):
        (tmp_path / "clinvar").mkdir()
        result = scan_data_source_availability(base_dir=tmp_path)
        assert result["clinvar"]["exists"] is True
        assert result["clinvar"]["file_count"] == 0

    def test_files_counted(self, tmp_path):
        clinvar_dir = tmp_path / "clinvar"
        clinvar_dir.mkdir()
        (clinvar_dir / "clinvar.vcf.gz").write_bytes(b"data" * 1000)
        result = scan_data_source_availability(base_dir=tmp_path)
        assert result["clinvar"]["file_count"] == 1
