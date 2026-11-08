"""claims are blocks

Revision ID: 5e2a9c1f7b30
Revises: 0b1c7d5a9e42
Create Date: 2026-11-08

"""

import sqlalchemy as sa
from alembic import op

revision = "5e2a9c1f7b30"
down_revision = "0b1c7d5a9e42"
branch_labels = None
depends_on = None


def upgrade():
    # Every existing claim is one tile: (x, y) becomes the block [x, x+1) x [y, y+1).
    op.alter_column("claim", "x", new_column_name="x0")
    op.alter_column("claim", "y", new_column_name="y0")
    op.add_column("claim", sa.Column("x1", sa.Integer()))
    op.add_column("claim", sa.Column("y1", sa.Integer()))
    op.execute("UPDATE claim SET x1 = x0 + 1, y1 = y0 + 1")
    op.alter_column("claim", "x1", nullable=False)
    op.alter_column("claim", "y1", nullable=False)

    op.drop_index("one_live_claim_per_tile", table_name="claim")
    op.drop_constraint("tile_within_canvas", "claim", type_="check")
    op.create_check_constraint(
        "block_within_canvas",
        "claim",
        "0 <= x0 AND x0 < x1 AND x1 <= 100 AND 0 <= y0 AND y0 < y1 AND y1 <= 100",
    )
    op.execute(
        "ALTER TABLE claim ADD CONSTRAINT no_overlapping_live_claims"
        " EXCLUDE USING gist (int4range(x0, x1) WITH &&, int4range(y0, y1) WITH &&)"
        " WHERE (status IN ('held', 'confirmed'))"
    )


def downgrade():
    # Lossy: a wider block shrinks to its top-left tile.
    op.drop_constraint("no_overlapping_live_claims", "claim")
    op.drop_constraint("block_within_canvas", "claim", type_="check")
    op.drop_column("claim", "y1")
    op.drop_column("claim", "x1")
    op.alter_column("claim", "y0", new_column_name="y")
    op.alter_column("claim", "x0", new_column_name="x")
    op.create_check_constraint(
        "tile_within_canvas", "claim", "x >= 0 AND x < 100 AND y >= 0 AND y < 100"
    )
    op.create_index(
        "one_live_claim_per_tile",
        "claim",
        ["x", "y"],
        unique=True,
        postgresql_where=sa.text("status IN ('held', 'confirmed')"),
    )
