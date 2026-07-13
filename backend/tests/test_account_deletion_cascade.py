"""Proves the User -> GeneticAnalysis delete cascade (U7) removes a user's
own data while leaving shared annotation caches untouched.

conftest.py globally stubs backend.db.models / backend.db.database with
duck-typed fakes for the rest of the suite; these tests load the real
modules (bypassing the stub) to exercise actual SQLAlchemy cascade behavior
against an in-memory SQLite engine, mirroring
test_analysis_variant_defaults.py's approach.
"""
import importlib
import sys

import pytest
from sqlalchemy import create_engine, event
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

# Pre-existing, unrelated model quirk: SharedVariantAnnotation.marker_id
# declares both index=True (auto-name ix_shared_variant_annotations_marker_id)
# and an explicit same-named Index() in __table_args__, producing two Index
# objects with an identical name. create_all() on a fresh schema then emits
# two CREATE INDEX statements for that one name, which SQLite (and Postgres)
# both reject. Not a U7 concern — just drop the duplicate so tables can be
# created here.
_dupe_annotation_indexes = [
    idx for idx in _real_models.SharedVariantAnnotation.__table__.indexes
    if idx.name == 'ix_shared_variant_annotations_marker_id'
]
for _idx in _dupe_annotation_indexes[1:]:
    _real_models.SharedVariantAnnotation.__table__.indexes.discard(_idx)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")

    # SQLite ignores FK constraints unless enabled per-connection — required
    # for the DB-level ON DELETE CASCADE on the 14 insight tables, which have
    # no ORM-level relationship from GeneticAnalysis to cascade through.
    @event.listens_for(engine, "connect")
    def _enable_fk_pragma(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    # Only the tables under test — the full metadata includes Postgres-only
    # column types (e.g. ARRAY) that SQLite's DDL compiler can't render.
    # SavedVariant/Notification/DashboardShare are otherwise-unused here, but
    # User's cascade_iterator lazy-loads every cascade="delete"-configured
    # relationship on User when session.delete(user) is flushed, so their
    # tables must exist even though these tests never populate them.
    tables = [
        _real_models.User.__table__,
        _real_models.GeneticAnalysis.__table__,
        _real_models.GeneticMarker.__table__,
        _real_models.AnalysisVariant.__table__,
        _real_models.SharedVariantAnnotation.__table__,
        _real_models.VariantAnnotation.__table__,
        _real_models.HealthRisk.__table__,
        _real_models.DrugResponse.__table__,
        _real_models.GnomadVariant.__table__,
        _real_models.ClinVarVariant.__table__,
        _real_models.SavedVariant.__table__,
        _real_models.Notification.__table__,
        _real_models.DashboardShare.__table__,
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


def _make_marker(db):
    marker = _real_models.GeneticMarker(
        rsid="rs1", chromosome="1", position=100, ref_allele="A", alt_alleles="G"
    )
    db.add(marker)
    db.flush()
    return marker


class TestUserDeletionCascade:
    def test_deleting_user_with_existing_analysis_does_not_raise(self, session):
        user = _make_user(session)
        _make_analysis(session, user)

        session.delete(user)
        session.commit()

        assert session.query(_real_models.User).count() == 0

    def test_deleting_user_deletes_their_analysis(self, session):
        user = _make_user(session)
        analysis = _make_analysis(session, user)
        analysis_id = analysis.id

        session.delete(user)
        session.commit()

        assert session.query(_real_models.GeneticAnalysis).filter_by(id=analysis_id).first() is None


class TestUserDeletionCascadeToInsightsAndVariants:
    @pytest.fixture
    def scenario(self, session):
        user = _make_user(session)
        analysis = _make_analysis(session, user)
        marker = _make_marker(session)

        variant = _real_models.AnalysisVariant(analysis_id=analysis.id, marker_id=marker.id, genotype="0/1")
        health_risk = _real_models.HealthRisk(
            analysis_id=analysis.id, condition="type 2 diabetes", risk_level="moderate"
        )
        drug_response = _real_models.DrugResponse(analysis_id=analysis.id, gene="CYP2D6", drug="codeine")
        session.add_all([variant, health_risk, drug_response])
        session.commit()

        ids = {
            "variant_id": variant.id,
            "health_risk_id": health_risk.id,
            "drug_response_id": drug_response.id,
            "marker_id": marker.id,
        }

        session.delete(user)
        session.commit()
        return session, ids

    def test_deleting_user_deletes_analysis_variant_rows(self, scenario):
        session, ids = scenario
        assert session.query(_real_models.AnalysisVariant).filter_by(id=ids["variant_id"]).first() is None

    def test_deleting_user_deletes_health_risk_rows(self, scenario):
        session, ids = scenario
        assert session.query(_real_models.HealthRisk).filter_by(id=ids["health_risk_id"]).first() is None

    def test_deleting_user_deletes_drug_response_rows(self, scenario):
        session, ids = scenario
        assert session.query(_real_models.DrugResponse).filter_by(id=ids["drug_response_id"]).first() is None

    def test_deleting_user_leaves_genetic_marker_intact(self, scenario):
        session, ids = scenario
        assert session.query(_real_models.GeneticMarker).filter_by(id=ids["marker_id"]).first() is not None


class TestUserDeletionLeavesSharedCachesIntact:
    def test_deleting_user_leaves_shared_variant_annotation_intact(self, session):
        user = _make_user(session)
        _make_analysis(session, user)
        marker = _make_marker(session)
        shared = _real_models.SharedVariantAnnotation(marker_id=marker.id, rsid=marker.rsid)
        session.add(shared)
        session.commit()
        shared_id = shared.id

        session.delete(user)
        session.commit()

        assert session.query(_real_models.SharedVariantAnnotation).filter_by(id=shared_id).first() is not None

    def test_deleting_user_leaves_gnomad_variant_intact(self, session):
        user = _make_user(session)
        _make_analysis(session, user)
        gnomad = _real_models.GnomadVariant(id=1, chrom="1", pos=100, ref="A", alt="G")
        session.add(gnomad)
        session.commit()

        session.delete(user)
        session.commit()

        assert session.query(_real_models.GnomadVariant).filter_by(id=1).first() is not None

    def test_deleting_user_leaves_clinvar_variant_intact(self, session):
        user = _make_user(session)
        _make_analysis(session, user)
        clinvar = _real_models.ClinVarVariant(id=1, rsid="rs1")
        session.add(clinvar)
        session.commit()

        session.delete(user)
        session.commit()

        assert session.query(_real_models.ClinVarVariant).filter_by(id=1).first() is not None
