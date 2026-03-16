"""Add is_admin to users and panel_marker_configs table

Revision ID: add_admin_panel_config
Revises: standardize_statuses_001
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_admin_panel_config'
down_revision = 'standardize_statuses_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add is_admin to users (if not exists)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='is_admin'"
    ))
    if not result.fetchone():
        op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=True, server_default='false'))

    # Create panel_marker_configs table (if not exists)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name='panel_marker_configs'"
    ))
    if not result.fetchone():
        op.create_table(
            'panel_marker_configs',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('panel_id', sa.String(), nullable=False, index=True),
            sa.Column('rsid', sa.String(), nullable=False),
            sa.Column('gene', sa.String(), nullable=True),
            sa.Column('description', sa.String(), nullable=True),
            sa.Column('category', sa.String(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_panel_marker_panel_rsid', 'panel_marker_configs', ['panel_id', 'rsid'], unique=True)

    # Make current user an admin
    op.execute(
        "UPDATE users SET is_admin = true WHERE email = 'elliotalderson710@gmail.com'"
    )

    # Seed default marker configurations (only if empty)
    result = conn.execute(sa.text("SELECT COUNT(*) FROM panel_marker_configs"))
    count = result.scalar()
    if count == 0:
        op.execute("""
            INSERT INTO panel_marker_configs (panel_id, rsid, gene, description, category) VALUES
        -- Methylation panel markers
        ('methylation', 'rs1801133', 'MTHFR', 'C677T - Reduced folate metabolism', 'folate_cycle'),
        ('methylation', 'rs1801131', 'MTHFR', 'A1298C - Reduced folate metabolism', 'folate_cycle'),
        ('methylation', 'rs4680', 'COMT', 'Val158Met - Catechol-O-methyltransferase', 'methylation_enzymes'),
        ('methylation', 'rs1805087', 'MTR', 'A2756G - Methionine synthase', 'methylation_enzymes'),
        ('methylation', 'rs1801394', 'MTRR', 'A66G - Methionine synthase reductase', 'methylation_enzymes'),
        ('methylation', 'rs234706', 'CBS', 'C699T - Cystathionine beta-synthase', 'transsulfuration'),
        ('methylation', 'rs2851391', 'CBS', 'CBS variant', 'transsulfuration'),
        -- Detox panel markers (Phase I)
        ('detox', 'rs2606345', 'CYP1A1', 'CYP1A1 Phase I oxidation', 'phase1'),
        ('detox', 'rs762551', 'CYP1A2', 'CYP1A2 Caffeine metabolism', 'phase1'),
        ('detox', 'rs3892097', 'CYP2D6', 'CYP2D6 Drug metabolism', 'phase1'),
        ('detox', 'rs1799853', 'CYP2C9', 'CYP2C9 Warfarin metabolism', 'phase1'),
        ('detox', 'rs4244285', 'CYP2C19', 'CYP2C19 Clopidogrel metabolism', 'phase1'),
        ('detox', 'rs2740574', 'CYP3A4', 'CYP3A4 Major drug metabolism', 'phase1'),
        -- Detox panel markers (Phase II)
        ('detox', 'rs1695', 'GSTP1', 'GSTP1 Glutathione conjugation', 'phase2'),
        ('detox', 'rs4148323', 'UGT1A1', 'UGT1A1 Glucuronidation', 'phase2'),
        ('detox', 'rs4986782', 'NAT1', 'NAT1 Acetylation', 'phase2'),
        ('detox', 'rs1799930', 'NAT2', 'NAT2 Acetylation', 'phase2'),
        ('detox', 'rs9282861', 'SULT1A1', 'SULT1A1 Sulfation', 'phase2'),
        -- Detox panel markers (Phase III)
        ('detox', 'rs1045642', 'ABCB1', 'ABCB1/MDR1 Drug transport', 'phase3'),
        ('detox', 'rs717620', 'ABCC2', 'ABCC2/MRP2 Organic anion transport', 'phase3'),
        ('detox', 'rs4149056', 'SLCO1B1', 'SLCO1B1 Hepatic uptake', 'phase3'),
        -- Health panel markers
        ('health', 'rs429358', 'APOE', 'APOE e4 - Alzheimer risk', 'cardiovascular'),
        ('health', 'rs7412', 'APOE', 'APOE e2 - Lipid metabolism', 'cardiovascular'),
        ('health', 'rs1801282', 'PPARG', 'Pro12Ala - Type 2 diabetes', 'metabolic'),
        ('health', 'rs9939609', 'FTO', 'FTO obesity risk', 'metabolic'),
        -- Sports panel markers
        ('sports', 'rs1815739', 'ACTN3', 'R577X - Power vs endurance', 'performance'),
        ('sports', 'rs4340', 'ACE', 'I/D - Endurance capacity', 'performance'),
        ('sports', 'rs8192678', 'PPARGC1A', 'Mitochondrial biogenesis', 'performance'),
        -- Drug response markers
        ('drug_responses', 'rs9923231', 'VKORC1', 'Warfarin sensitivity', 'anticoagulants'),
        ('drug_responses', 'rs4149056', 'SLCO1B1', 'Statin myopathy risk', 'statins'),
        ('drug_responses', 'rs12248560', 'CYP2C19', 'Clopidogrel metabolism', 'antiplatelet')
    """)


def downgrade() -> None:
    op.drop_index('ix_panel_marker_panel_rsid', 'panel_marker_configs')
    op.drop_table('panel_marker_configs')
    op.drop_column('users', 'is_admin')
