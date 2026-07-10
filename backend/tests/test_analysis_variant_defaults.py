"""Model-level defaults for the U2 hot columns (AnalysisVariant.genotype/info,
GeneticMarker.alt_alleles). conftest.py globally stubs backend.db.models /
backend.db.database with duck-typed fakes for the rest of the suite, so these
tests load the real modules fresh (bypassing the stub) to exercise real
SQLAlchemy Column defaults against an in-memory SQLite engine.
"""
import importlib
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def _load_real_db_modules():
    saved = {
        'backend.db.database': sys.modules.get('backend.db.database'),
        'backend.db.models': sys.modules.get('backend.db.models'),
    }
    sys.modules.pop('backend.db.database', None)
    sys.modules.pop('backend.db.models', None)
    try:
        real_database = importlib.import_module('backend.db.database')
        real_models = importlib.import_module('backend.db.models')
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)
    return real_database, real_models


_real_database, _real_models = _load_real_db_modules()


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    # Only the tables under test — the full metadata includes Postgres-only
    # column types (e.g. ARRAY) that SQLite's DDL compiler can't render.
    tables = [
        _real_models.User.__table__,
        _real_models.GeneticAnalysis.__table__,
        _real_models.GeneticMarker.__table__,
        _real_models.AnalysisVariant.__table__,
    ]
    _real_database.Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()


def _make_user(db):
    user = _real_models.User(email="a@example.com", username="alice")
    db.add(user)
    db.flush()
    return user


def _make_analysis(db, user):
    analysis = _real_models.GeneticAnalysis(user_id=user.id, filename="f.vcf", file_type="vcf")
    db.add(analysis)
    db.flush()
    return analysis


class TestAnalysisVariantDefaults:
    def test_genotype_defaults_to_no_call_when_omitted(self, session):
        user = _make_user(session)
        analysis = _make_analysis(session, user)
        marker = _real_models.GeneticMarker(rsid="rs1", chromosome="1", position=100, ref_allele="A")
        session.add(marker)
        session.flush()

        variant = _real_models.AnalysisVariant(analysis_id=analysis.id, marker_id=marker.id)
        session.add(variant)
        session.commit()

        assert variant.genotype == "./."

    def test_info_defaults_to_empty_dict_when_omitted(self, session):
        user = _make_user(session)
        analysis = _make_analysis(session, user)
        marker = _real_models.GeneticMarker(rsid="rs2", chromosome="1", position=200, ref_allele="A")
        session.add(marker)
        session.flush()

        variant = _real_models.AnalysisVariant(analysis_id=analysis.id, marker_id=marker.id)
        session.add(variant)
        session.commit()

        assert variant.info == {}

    def test_alt_alleles_defaults_to_empty_string_when_omitted(self, session):
        marker = _real_models.GeneticMarker(rsid="rs3", chromosome="1", position=300, ref_allele="A")
        session.add(marker)
        session.commit()

        assert marker.alt_alleles == ""


class TestLegacyNullBackfill:
    def test_backfilled_info_supports_get_without_attribute_error(self):
        # Builds the pre-migration table shape directly (info nullable, no
        # default) so a true SQL NULL can be inserted — the JSON column type's
        # Python-level None-to-'null' coercion would otherwise mask a real
        # legacy NULL when going through the ORM. Then runs the exact backfill
        # SQL from 036_hot_column_defaults.upgrade() and reads back via the
        # real ORM model, matching what happens against the production DB.
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            # AnalysisVariant.marker uses lazy="joined", so the read-back
            # query always joins genetic_markers — it must exist too.
            conn.execute(text(
                "CREATE TABLE genetic_markers ("
                "id INTEGER PRIMARY KEY, rsid TEXT, chromosome TEXT, position INTEGER, "
                "ref_allele TEXT, alt_alleles TEXT, gene_symbol TEXT, created_at TEXT, upload_count INTEGER)"
            ))
            conn.execute(text(
                "INSERT INTO genetic_markers (id, rsid, chromosome, position, ref_allele, alt_alleles) "
                "VALUES (1, 'rs4', '1', 400, 'A', 'G')"
            ))
            conn.execute(text(
                "CREATE TABLE analysis_variants ("
                "id INTEGER PRIMARY KEY, analysis_id INTEGER, marker_id INTEGER, "
                "genotype TEXT, quality TEXT, filter_status TEXT, info TEXT, created_at TEXT)"
            ))
            conn.execute(text(
                "INSERT INTO analysis_variants (id, analysis_id, marker_id, genotype, info) "
                "VALUES (1, 1, 1, 'AA', NULL)"
            ))
            conn.execute(text("UPDATE analysis_variants SET info = '{}' WHERE info IS NULL"))

        Session = sessionmaker(bind=engine)
        db = Session()
        reloaded = db.get(_real_models.AnalysisVariant, 1)
        db.close()

        assert reloaded.info.get("original_genotype") is None
