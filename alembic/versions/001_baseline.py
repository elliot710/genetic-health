"""Baseline migration — squashed from 37 historical migrations.

This single migration creates the entire schema from scratch.
The archived originals are preserved in alembic/versions/_archived/ for reference.

Revision ID: 001_baseline
Revises: (none)
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ──────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── users ───────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String, unique=True, nullable=False),
        sa.Column("username", sa.String, unique=True, nullable=False),
        sa.Column("hashed_password", sa.String, nullable=False),
        sa.Column("full_name", sa.String),
        sa.Column("avatar_url", sa.String),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("is_verified", sa.Boolean, server_default=sa.text("false")),
        sa.Column("is_admin", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # ── genetic_analyses ────────────────────────────────────────────────
    op.create_table(
        "genetic_analyses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("file_type", sa.String, nullable=False),
        sa.Column("analysis_results", sa.JSON),
        sa.Column("upload_date", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("analysis_status", sa.String, server_default=sa.text("'pending'")),
        sa.Column("progress_percentage", sa.Integer, server_default=sa.text("0")),
        sa.Column("total_variants", sa.Integer, server_default=sa.text("0")),
        sa.Column("processed_variants", sa.Integer, server_default=sa.text("0")),
        sa.Column("current_step", sa.String, server_default=sa.text("'initializing'")),
        sa.Column("estimated_completion", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_genetic_analyses_id", "genetic_analyses", ["id"])

    # ── genetic_markers ─────────────────────────────────────────────────
    op.create_table(
        "genetic_markers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("rsid", sa.String, unique=True, nullable=False),
        sa.Column("chromosome", sa.String, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("ref_allele", sa.String, nullable=False),
        sa.Column("alt_alleles", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("upload_count", sa.Integer, server_default=sa.text("1")),
    )
    op.create_index("ix_genetic_markers_id", "genetic_markers", ["id"])
    op.create_index("ix_genetic_markers_rsid", "genetic_markers", ["rsid"], unique=True)
    op.create_index("ix_genetic_markers_chr_pos", "genetic_markers", ["chromosome", "position"])

    # ── analysis_variants ───────────────────────────────────────────────
    op.create_table(
        "analysis_variants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("marker_id", sa.Integer, sa.ForeignKey("genetic_markers.id"), nullable=False),
        sa.Column("genotype", sa.String),
        sa.Column("quality", sa.String),
        sa.Column("filter_status", sa.String),
        sa.Column("info", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analysis_variants_id", "analysis_variants", ["id"])
    op.create_index("ix_analysis_variants_analysis_id", "analysis_variants", ["analysis_id"])
    op.create_index("ix_analysis_variants_analysis_marker", "analysis_variants", ["analysis_id", "marker_id"])

    # ── shared_variant_annotations ──────────────────────────────────────
    op.create_table(
        "shared_variant_annotations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("marker_id", sa.Integer, sa.ForeignKey("genetic_markers.id"), nullable=False, unique=True),
        sa.Column("rsid", sa.String, nullable=False, unique=True),
        sa.Column("ensembl_data", sa.JSON),
        sa.Column("clinvar_data", sa.JSON),
        sa.Column("pharmgkb_data", sa.JSON),
        sa.Column("snpedia_data", sa.JSON),
        sa.Column("litvar_data", sa.JSON),
        sa.Column("alpha_missense_data", sa.JSON),
        sa.Column("clinvar_local_data", sa.JSON),
        sa.Column("gnomad_data", sa.JSON),
        sa.Column("thousand_genomes_data", sa.JSON),
        sa.Column("chembl_data", sa.JSON),
        sa.Column("fda_drug_data", sa.JSON),
        sa.Column("alphafold_data", sa.JSON),
        sa.Column("first_annotated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_updated_at", sa.DateTime(timezone=True)),
        sa.Column("annotation_status", sa.String, server_default=sa.text("'completed'")),
        sa.Column("total_api_calls", sa.Integer, server_default=sa.text("0")),
        sa.Column("failed_sources", sa.JSON, server_default=sa.text("'[]'")),
        sa.Column("usage_count", sa.Integer, server_default=sa.text("0")),
    )
    op.create_index("ix_shared_variant_annotations_id", "shared_variant_annotations", ["id"])
    op.create_index("ix_shared_variant_annotations_marker_id", "shared_variant_annotations", ["marker_id"], unique=True)
    op.create_index("ix_shared_variant_annotations_rsid", "shared_variant_annotations", ["rsid"], unique=True)

    # ── variant_annotations ─────────────────────────────────────────────
    op.create_table(
        "variant_annotations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_variant_id", sa.Integer, sa.ForeignKey("analysis_variants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shared_annotation_id", sa.Integer, sa.ForeignKey("shared_variant_annotations.id")),
        sa.Column("rsid", sa.String, nullable=False),
        sa.Column("user_notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("analysis_id", "analysis_variant_id", name="uq_variant_annotations_analysis_variant"),
    )
    op.create_index("ix_variant_annotations_id", "variant_annotations", ["id"])
    op.create_index("ix_variant_annotations_analysis_id", "variant_annotations", ["analysis_id"])
    op.create_index("ix_variant_annotations_rsid", "variant_annotations", ["rsid"])

    # ── 13 insight tables (all cascade-delete on analysis) ──────────────
    op.create_table(
        "health_risks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("condition", sa.String, nullable=False),
        sa.Column("risk_level", sa.String, nullable=False),
        sa.Column("risk_score", sa.String),
        sa.Column("associated_variants", sa.JSON),
        sa.Column("recommendations", sa.JSON),
    )
    op.create_index("ix_health_risks_id", "health_risks", ["id"])
    op.create_index("ix_health_risks_analysis_id", "health_risks", ["analysis_id"])

    op.create_table(
        "drug_responses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gene", sa.String, nullable=False),
        sa.Column("drug", sa.String, nullable=False),
        sa.Column("response_type", sa.String),
        sa.Column("recommendations", sa.Text),
        sa.Column("variants_involved", sa.JSON),
    )
    op.create_index("ix_drug_responses_id", "drug_responses", ["id"])
    op.create_index("ix_drug_responses_analysis_id", "drug_responses", ["analysis_id"])

    op.create_table(
        "physical_traits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trait_name", sa.String, nullable=False),
        sa.Column("trait_category", sa.String, nullable=False),
        sa.Column("genetic_result", sa.String, nullable=False),
        sa.Column("confidence", sa.String),
        sa.Column("associated_variants", sa.JSON),
        sa.Column("description", sa.Text),
    )
    op.create_index("ix_physical_traits_id", "physical_traits", ["id"])
    op.create_index("ix_physical_traits_analysis_id", "physical_traits", ["analysis_id"])

    op.create_table(
        "nutrition_traits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nutrient", sa.String, nullable=False),
        sa.Column("metabolism_type", sa.String),
        sa.Column("dietary_recommendations", sa.JSON),
        sa.Column("associated_variants", sa.JSON),
        sa.Column("sensitivity_level", sa.String),
    )
    op.create_index("ix_nutrition_traits_id", "nutrition_traits", ["id"])
    op.create_index("ix_nutrition_traits_analysis_id", "nutrition_traits", ["analysis_id"])

    op.create_table(
        "sports_performance",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("performance_category", sa.String, nullable=False),
        sa.Column("genetic_advantage", sa.String),
        sa.Column("sport_recommendations", sa.JSON),
        sa.Column("associated_variants", sa.JSON),
        sa.Column("training_advice", sa.Text),
    )
    op.create_index("ix_sports_performance_id", "sports_performance", ["id"])
    op.create_index("ix_sports_performance_analysis_id", "sports_performance", ["analysis_id"])

    op.create_table(
        "cognitive_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cognitive_domain", sa.String, nullable=False),
        sa.Column("genetic_score", sa.String),
        sa.Column("percentile", sa.Integer),
        sa.Column("associated_variants", sa.JSON),
        sa.Column("enhancement_suggestions", sa.JSON),
    )
    op.create_index("ix_cognitive_profiles_id", "cognitive_profiles", ["id"])
    op.create_index("ix_cognitive_profiles_analysis_id", "cognitive_profiles", ["analysis_id"])

    op.create_table(
        "personality_traits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trait_name", sa.String, nullable=False),
        sa.Column("genetic_tendency", sa.String),
        sa.Column("confidence_level", sa.String),
        sa.Column("associated_variants", sa.JSON),
        sa.Column("behavioral_insights", sa.JSON),
    )
    op.create_index("ix_personality_traits_id", "personality_traits", ["id"])
    op.create_index("ix_personality_traits_analysis_id", "personality_traits", ["analysis_id"])

    op.create_table(
        "ancestry_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("population", sa.String, nullable=False),
        sa.Column("percentage", sa.String),
        sa.Column("confidence", sa.String),
        sa.Column("geographic_origin", sa.String),
        sa.Column("associated_variants", sa.JSON),
        sa.Column("composition", sa.JSON),
        sa.Column("maternal_haplogroup", sa.JSON),
        sa.Column("paternal_haplogroup", sa.JSON),
        sa.Column("neanderthal_variants", sa.JSON),
    )
    op.create_index("ix_ancestry_results_id", "ancestry_results", ["id"])
    op.create_index("ix_ancestry_results_analysis_id", "ancestry_results", ["analysis_id"])

    op.create_table(
        "carrier_status",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("condition", sa.String, nullable=False),
        sa.Column("carrier_status", sa.String),
        sa.Column("inheritance_pattern", sa.String),
        sa.Column("associated_variants", sa.JSON),
        sa.Column("genetic_counseling_recommended", sa.Boolean, server_default=sa.text("false")),
    )
    op.create_index("ix_carrier_status_id", "carrier_status", ["id"])
    op.create_index("ix_carrier_status_analysis_id", "carrier_status", ["analysis_id"])

    op.create_table(
        "wellness_metrics",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_name", sa.String, nullable=False),
        sa.Column("genetic_predisposition", sa.String),
        sa.Column("optimization_score", sa.String),
        sa.Column("lifestyle_recommendations", sa.JSON),
        sa.Column("associated_variants", sa.JSON),
    )
    op.create_index("ix_wellness_metrics_id", "wellness_metrics", ["id"])
    op.create_index("ix_wellness_metrics_analysis_id", "wellness_metrics", ["analysis_id"])

    op.create_table(
        "methylation_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gene", sa.String, nullable=False),
        sa.Column("variant", sa.String),
        sa.Column("methylation_capacity", sa.String),
        sa.Column("supplement_recommendations", sa.JSON),
        sa.Column("associated_variants", sa.JSON),
    )
    op.create_index("ix_methylation_profiles_id", "methylation_profiles", ["id"])
    op.create_index("ix_methylation_profiles_analysis_id", "methylation_profiles", ["analysis_id"])

    op.create_table(
        "detoxification_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("detox_phase", sa.String, nullable=False),
        sa.Column("gene", sa.String, nullable=False),
        sa.Column("detox_capacity", sa.String),
        sa.Column("toxin_sensitivity", sa.String),
        sa.Column("support_recommendations", sa.JSON),
        sa.Column("associated_variants", sa.JSON),
    )
    op.create_index("ix_detoxification_profiles_id", "detoxification_profiles", ["id"])
    op.create_index("ix_detoxification_profiles_analysis_id", "detoxification_profiles", ["analysis_id"])

    # Rare + uncommon mutations
    op.create_table(
        "rare_mutations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mutation_type", sa.String, nullable=False),
        sa.Column("gene", sa.String, nullable=False),
        sa.Column("mutation_name", sa.String),
        sa.Column("clinical_significance", sa.String),
        sa.Column("disease_association", sa.String),
        sa.Column("penetrance", sa.String),
        sa.Column("inheritance_pattern", sa.String),
        sa.Column("population_frequency", sa.Float),
        sa.Column("clinical_actions", sa.JSON),
        sa.Column("specialist_referral", sa.Boolean, server_default=sa.text("false")),
        sa.Column("genetic_counseling_urgent", sa.Boolean, server_default=sa.text("false")),
        sa.Column("monitoring_recommendations", sa.JSON),
        sa.Column("family_screening_recommended", sa.Boolean, server_default=sa.text("false")),
        sa.Column("associated_variants", sa.JSON),
    )
    op.create_index("ix_rare_mutations_id", "rare_mutations", ["id"])
    op.create_index("ix_rare_mutations_analysis_id", "rare_mutations", ["analysis_id"])

    op.create_table(
        "uncommon_mutations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mutation_type", sa.String, nullable=False),
        sa.Column("gene", sa.String, nullable=False),
        sa.Column("mutation_name", sa.String),
        sa.Column("clinical_significance", sa.String),
        sa.Column("trait_association", sa.String),
        sa.Column("effect_size", sa.String),
        sa.Column("population_frequency", sa.Float),
        sa.Column("research_status", sa.String),
        sa.Column("lifestyle_implications", sa.JSON),
        sa.Column("monitoring_suggestions", sa.JSON),
        sa.Column("research_participation", sa.String),
        sa.Column("follow_up_timeline", sa.String),
        sa.Column("associated_variants", sa.JSON),
    )
    op.create_index("ix_uncommon_mutations_id", "uncommon_mutations", ["id"])
    op.create_index("ix_uncommon_mutations_analysis_id", "uncommon_mutations", ["analysis_id"])

    # ── Admin / config tables ───────────────────────────────────────────
    op.create_table(
        "panel_marker_configs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("panel_id", sa.String, nullable=False),
        sa.Column("rsid", sa.String, nullable=False),
        sa.Column("gene", sa.String),
        sa.Column("description", sa.String),
        sa.Column("category", sa.String),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("is_auto_discovered", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_panel_marker_configs_id", "panel_marker_configs", ["id"])
    op.create_index("ix_panel_marker_configs_panel_id", "panel_marker_configs", ["panel_id"])
    op.create_index("ix_panel_marker_panel_rsid", "panel_marker_configs", ["panel_id", "rsid"], unique=True)

    op.create_table(
        "variant_mappings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("map_type", sa.String, nullable=False),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("is_auto_discovered", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_variant_mappings_id", "variant_mappings", ["id"])
    op.create_index("ix_variant_mappings_category", "variant_mappings", ["category"])
    op.create_index("ix_variant_mappings_cat_type_key", "variant_mappings", ["category", "map_type", "key"], unique=True)

    op.create_table(
        "variant_lookup_cache",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("variant_id", sa.String, unique=True, nullable=False),
        sa.Column("found", sa.Boolean, server_default=sa.text("false")),
        sa.Column("response_data", sa.JSON),
        sa.Column("raw_annotations", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("lookup_count", sa.Integer, server_default=sa.text("1")),
    )
    op.create_index("ix_variant_lookup_cache_id", "variant_lookup_cache", ["id"])
    op.create_index("ix_variant_lookup_cache_variant_id", "variant_lookup_cache", ["variant_id"], unique=True)

    op.create_table(
        "annotation_source_configs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_name", sa.String, unique=True, nullable=False),
        sa.Column("display_name", sa.String, nullable=False),
        sa.Column("is_enabled", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("description", sa.String),
        sa.Column("rate_limit", sa.Float),
        sa.Column("priority", sa.Integer, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_annotation_source_configs_id", "annotation_source_configs", ["id"])
    op.create_index("ix_annotation_source_configs_source_name", "annotation_source_configs", ["source_name"], unique=True)

    op.create_table(
        "pending_discoveries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("discovery_type", sa.String, nullable=False),
        sa.Column("rsid", sa.String, nullable=False),
        sa.Column("gene", sa.String),
        sa.Column("panel_id", sa.String),
        sa.Column("description", sa.String),
        sa.Column("category", sa.String),
        sa.Column("map_type", sa.String),
        sa.Column("mapping_category", sa.String),
        sa.Column("mapping_data", sa.JSON),
        sa.Column("source_data", sa.JSON),
        sa.Column("status", sa.String, server_default=sa.text("'pending'"), nullable=False),
        sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.String),
        sa.Column("discovered_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("lookup_count", sa.Integer, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_pending_discoveries_id", "pending_discoveries", ["id"])
    op.create_index("ix_pending_discoveries_rsid", "pending_discoveries", ["rsid"])
    op.create_index("ix_pending_discoveries_status", "pending_discoveries", ["status"])
    op.create_index("ix_pending_discoveries_type_rsid_panel", "pending_discoveries", ["discovery_type", "rsid", "panel_id"], unique=True)

    op.create_table(
        "category_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("rule_type", sa.String, nullable=False),
        sa.Column("rule_value", sa.Text, nullable=False),
        sa.Column("priority", sa.Integer, server_default=sa.text("50")),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("mapping_data_template", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_category_rules_id", "category_rules", ["id"])
    op.create_index("ix_category_rules_category", "category_rules", ["category"])
    op.create_index("ix_category_rules_cat_type", "category_rules", ["category", "rule_type"])

    # ── ClinVar local data tables ───────────────────────────────────────
    op.create_table(
        "clinvar_variants",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("rsid", sa.String, nullable=False),
        sa.Column("allele_id", sa.String),
        sa.Column("variation_id", sa.String),
        sa.Column("clinical_significance", sa.String),
        sa.Column("review_status", sa.String),
        sa.Column("conditions", sa.String),
        sa.Column("origin", sa.String),
        sa.Column("variation_type", sa.String),
        sa.Column("gene", sa.String),
        sa.Column("gene_id", sa.String),
        sa.Column("chromosome", sa.String),
        sa.Column("start_pos", sa.Integer),
        sa.Column("stop_pos", sa.Integer),
        sa.Column("assembly", sa.String),
        sa.Column("rcv_accession", sa.String),
        sa.Column("phenotype_ids", sa.String),
        sa.Column("hgvs_nucleotide", sa.String),
        sa.Column("hgvs_protein", sa.String),
        sa.Column("molecular_consequence", sa.String),
        sa.Column("af_exac", sa.Float),
        sa.Column("af_tgp", sa.Float),
        sa.Column("af_esp", sa.Float),
        sa.Column("oncogenicity", sa.String),
        sa.Column("somatic_clinical_impact", sa.String),
        sa.Column("conflicting_classifications", sa.Text),
        sa.Column("data_source", sa.String, server_default=sa.text("'tsv'")),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_clinvar_variants_rsid", "clinvar_variants", ["rsid"])
    op.create_index("ix_clinvar_variants_gene", "clinvar_variants", ["gene"])
    op.create_index("ix_clinvar_variants_significance", "clinvar_variants", ["clinical_significance"])
    op.create_index("ix_clinvar_variants_rsid_allele", "clinvar_variants", ["rsid", "allele_id"])

    op.create_table(
        "clinvar_gene_conditions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("gene", sa.String, nullable=False),
        sa.Column("disease_name", sa.String, nullable=False),
        sa.Column("source_name", sa.String),
        sa.Column("source_id", sa.String),
        sa.Column("disease_mim", sa.String),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_clinvar_gene_conditions_gene", "clinvar_gene_conditions", ["gene"])

    op.create_table(
        "clinvar_gene_stats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("gene", sa.String, nullable=False, unique=True),
        sa.Column("gene_id", sa.String),
        sa.Column("total_submissions", sa.Integer, server_default=sa.text("0")),
        sa.Column("total_alleles", sa.Integer, server_default=sa.text("0")),
        sa.Column("pathogenic_likely_pathogenic", sa.Integer, server_default=sa.text("0")),
        sa.Column("uncertain_significance", sa.Integer, server_default=sa.text("0")),
        sa.Column("with_conflicts", sa.Integer, server_default=sa.text("0")),
        sa.Column("gene_mim", sa.String),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_clinvar_gene_stats_id", "clinvar_gene_stats", ["id"])
    op.create_index("ix_clinvar_gene_stats_gene", "clinvar_gene_stats", ["gene"], unique=True)

    # ── gnomAD local data tables ────────────────────────────────────────
    op.create_table(
        "gnomad_variants",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("chrom", sa.String, nullable=False),
        sa.Column("pos", sa.Integer, nullable=False),
        sa.Column("ref", sa.String, nullable=False),
        sa.Column("alt", sa.String, nullable=False),
        sa.Column("rsid", sa.String),
        sa.Column("variant_id", sa.String),
        sa.Column("variant_type", sa.String),
        sa.Column("filter_status", sa.String),
        sa.Column("af", sa.Float),
        sa.Column("ac", sa.Integer),
        sa.Column("an", sa.Integer),
        sa.Column("nhomalt", sa.Integer),
        sa.Column("af_afr", sa.Float),
        sa.Column("af_ami", sa.Float),
        sa.Column("af_amr", sa.Float),
        sa.Column("af_asj", sa.Float),
        sa.Column("af_eas", sa.Float),
        sa.Column("af_fin", sa.Float),
        sa.Column("af_mid", sa.Float),
        sa.Column("af_nfe", sa.Float),
        sa.Column("af_sas", sa.Float),
        sa.Column("af_remaining", sa.Float),
        sa.Column("cadd_raw", sa.Float),
        sa.Column("cadd_phred", sa.Float),
        sa.Column("sift_cat", sa.String),
        sa.Column("sift_val", sa.Float),
        sa.Column("polyphen_cat", sa.String),
        sa.Column("polyphen_val", sa.Float),
        sa.Column("phylop_primate", sa.Float),
        sa.Column("phylop_mammal", sa.Float),
        sa.Column("phylop_vertebrate", sa.Float),
        sa.Column("splice_ai_acc_gain", sa.Float),
        sa.Column("splice_ai_acc_loss", sa.Float),
        sa.Column("splice_ai_don_gain", sa.Float),
        sa.Column("splice_ai_don_loss", sa.Float),
        sa.Column("gene", sa.String),
        sa.Column("consequence", sa.String),
        sa.Column("impact", sa.String),
        sa.Column("hgvsc", sa.String),
        sa.Column("hgvsp", sa.String),
        sa.Column("annotations", sa.JSON),
        sa.Column("data_source", sa.String, server_default=sa.text("'tsv'")),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_gnomad_variants_rsid", "gnomad_variants", ["rsid"])
    op.create_index("ix_gnomad_variants_chrom_pos", "gnomad_variants", ["chrom", "pos"])
    op.create_index("ix_gnomad_variants_chrom_pos_ref_alt", "gnomad_variants", ["chrom", "pos", "ref", "alt"], unique=True)
    op.create_index("ix_gnomad_variants_gene", "gnomad_variants", ["gene"])
    op.create_index("ix_gnomad_variants_variant_id", "gnomad_variants", ["variant_id"])
    op.create_index("ix_gnomad_variants_cadd_phred", "gnomad_variants", ["cadd_phred"])

    op.create_table(
        "gnomad_gene_constraints",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("gene", sa.String, nullable=False, unique=True),
        sa.Column("transcript", sa.String),
        sa.Column("pli", sa.Float),
        sa.Column("loeuf", sa.Float),
        sa.Column("mis_z", sa.Float),
        sa.Column("syn_z", sa.Float),
        sa.Column("obs_lof", sa.Integer),
        sa.Column("exp_lof", sa.Float),
        sa.Column("obs_mis", sa.Integer),
        sa.Column("exp_mis", sa.Float),
        sa.Column("obs_syn", sa.Integer),
        sa.Column("exp_syn", sa.Float),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_gnomad_gene_constraints_gene", "gnomad_gene_constraints", ["gene"])

    # ── Ensembl local data tables ───────────────────────────────────────
    op.create_table(
        "ensembl_genes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("gene_id", sa.String, nullable=False, unique=True),
        sa.Column("gene_symbol", sa.String, nullable=False),
        sa.Column("chromosome", sa.String, nullable=False),
        sa.Column("start_pos", sa.BigInteger, nullable=False),
        sa.Column("end_pos", sa.BigInteger, nullable=False),
        sa.Column("strand", sa.SmallInteger),
        sa.Column("biotype", sa.String),
        sa.Column("description", sa.Text),
        sa.Column("transcript_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ensembl_genes_chr_range", "ensembl_genes", ["chromosome", "start_pos", "end_pos"])
    op.create_index("ix_ensembl_genes_gene_symbol", "ensembl_genes", ["gene_symbol"])

    op.create_table(
        "ensembl_vep_variants",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("rsid", sa.String, nullable=False, unique=True),
        sa.Column("chromosome", sa.String(5), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("ref_allele", sa.String(500), nullable=False),
        sa.Column("alt_alleles", sa.String(1000), nullable=False),
        sa.Column("variant_type", sa.String(20)),
        sa.Column("minor_allele", sa.String(50)),
        sa.Column("minor_allele_freq", sa.Float),
        sa.Column("ancestral_allele", sa.String(500)),
        sa.Column("clinical_significance", sa.ARRAY(sa.String)),
        sa.Column("evidence", sa.ARRAY(sa.String)),
        sa.Column("most_severe_consequence", sa.String(100)),
        sa.Column("impact", sa.String(20)),
        sa.Column("gene_symbol", sa.String(50)),
        sa.Column("vep_data", sa.JSON),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ensembl_vep_variants_rsid", "ensembl_vep_variants", ["rsid"], unique=True)
    op.create_index("ix_ensembl_vep_chr_pos", "ensembl_vep_variants", ["chromosome", "position"])

    # ── 1000 Genomes Phase 3 ───────────────────────────────────────────
    op.create_table(
        "thousand_genomes_variants",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("chrom", sa.String, nullable=False),
        sa.Column("pos", sa.Integer, nullable=False),
        sa.Column("ref", sa.String, nullable=False),
        sa.Column("alt", sa.String, nullable=False),
        sa.Column("rsid", sa.String),
        sa.Column("variant_type", sa.String),
        sa.Column("minor_allele", sa.String),
        sa.Column("maf", sa.Float),
        sa.Column("mac", sa.Integer),
        sa.Column("ancestral_allele", sa.String),
        sa.Column("af_afr", sa.Float),
        sa.Column("af_amr", sa.Float),
        sa.Column("af_eas", sa.Float),
        sa.Column("af_eur", sa.Float),
        sa.Column("af_sas", sa.Float),
        sa.Column("is_clinvar", sa.Boolean, server_default=sa.text("false")),
        sa.Column("is_1000g", sa.Boolean, server_default=sa.text("false")),
        sa.Column("data_source", sa.String, server_default=sa.text("'ensembl_vcf'")),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_1kg_rsid", "thousand_genomes_variants", ["rsid"])
    op.create_index("ix_1kg_chrom_pos", "thousand_genomes_variants", ["chrom", "pos"])
    op.create_index("ix_1kg_chrom_pos_ref_alt", "thousand_genomes_variants", ["chrom", "pos", "ref", "alt"], unique=True)
    op.create_index("ix_1kg_maf", "thousand_genomes_variants", ["maf"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("thousand_genomes_variants")
    op.drop_table("ensembl_vep_variants")
    op.drop_table("ensembl_genes")
    op.drop_table("gnomad_gene_constraints")
    op.drop_table("gnomad_variants")
    op.drop_table("clinvar_gene_stats")
    op.drop_table("clinvar_gene_conditions")
    op.drop_table("clinvar_variants")
    op.drop_table("category_rules")
    op.drop_table("pending_discoveries")
    op.drop_table("annotation_source_configs")
    op.drop_table("variant_lookup_cache")
    op.drop_table("variant_mappings")
    op.drop_table("panel_marker_configs")
    op.drop_table("uncommon_mutations")
    op.drop_table("rare_mutations")
    op.drop_table("detoxification_profiles")
    op.drop_table("methylation_profiles")
    op.drop_table("wellness_metrics")
    op.drop_table("carrier_status")
    op.drop_table("ancestry_results")
    op.drop_table("personality_traits")
    op.drop_table("cognitive_profiles")
    op.drop_table("sports_performance")
    op.drop_table("nutrition_traits")
    op.drop_table("physical_traits")
    op.drop_table("drug_responses")
    op.drop_table("health_risks")
    op.drop_table("variant_annotations")
    op.drop_table("shared_variant_annotations")
    op.drop_table("analysis_variants")
    op.drop_table("genetic_markers")
    op.drop_table("genetic_analyses")
    op.drop_table("users")
