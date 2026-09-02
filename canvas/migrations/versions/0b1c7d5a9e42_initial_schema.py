"""initial schema

Revision ID: 0b1c7d5a9e42
Revises:
Create Date: 2026-09-01

"""

import sqlalchemy as sa
from alembic import op

revision = "0b1c7d5a9e42"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "claim",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("colour", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "x >= 0 AND x < 100 AND y >= 0 AND y < 100", name="tile_within_canvas"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Partial, so a released claim stops owning its tile without being deleted.
    op.create_index(
        "one_live_claim_per_tile",
        "claim",
        ["x", "y"],
        unique=True,
        postgresql_where=sa.text("status IN ('held', 'confirmed')"),
    )


def downgrade():
    op.drop_index("one_live_claim_per_tile", table_name="claim")
    op.drop_table("claim")
