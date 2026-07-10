"""Convert health_risks.risk_score from String to Float.

Storing risk_score as a numeric type enables comparison queries,
aggregations, and correct sorting by severity. Values are stored
as float strings like "0.8" so the cast is safe for all existing rows.

Revision ID: 025_risk_score_float
Revises: 024_ancestry_subpop
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa

revision = "025_risk_score_float"
down_revision = "024_ancestry_subpop"
branch_labels = None
depends_on = None


def upgrade():
    # Populate any NULL risk_score values before changing type so the cast
    # doesn't fail on nothing-to-convert rows.
    op.execute(
        "UPDATE health_risks SET risk_score = '0.0' WHERE risk_score IS NULL"
    )

    # ALTER the column type using an explicit cast expression.
    # PostgreSQL requires USING when converting from text to numeric.
    op.execute(
        "ALTER TABLE health_risks "
        "ALTER COLUMN risk_score TYPE FLOAT "
        "USING risk_score::float"
    )


def downgrade():
    op.execute(
        "ALTER TABLE health_risks "
        "ALTER COLUMN risk_score TYPE VARCHAR(50) "
        "USING risk_score::text"
    )
