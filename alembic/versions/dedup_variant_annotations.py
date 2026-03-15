"""Deduplicate variant_annotations and add unique constraint

Revision ID: dedup_variant_ann
Revises: e5ec70b0bcb1
Create Date: 2026-03-15
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'dedup_variant_ann'
down_revision: Union[str, None] = 'e5ec70b0bcb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete duplicate rows using a fast CTE approach
    # (NOT IN subquery is extremely slow on large tables)
    op.execute("""
        DELETE FROM variant_annotations
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY analysis_id, analysis_variant_id
                    ORDER BY id
                ) AS rn
                FROM variant_annotations
            ) ranked
            WHERE rn > 1
        )
    """)

    # Add unique constraint to prevent future duplicates
    op.create_unique_constraint(
        'uq_variant_annotations_analysis_variant',
        'variant_annotations',
        ['analysis_id', 'analysis_variant_id']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_variant_annotations_analysis_variant',
        'variant_annotations',
        type_='unique'
    )
