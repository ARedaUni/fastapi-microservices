from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# The canvas is GRID_SIZE x GRID_SIZE tiles. A constant, not a setting: nothing
# resizes a canvas people have already drawn on.
GRID_SIZE = 100

# A claim in either state owns its block. `released` does not, which is what
# makes the exclusion constraint below partial -- a block whose hold lapsed has
# to be claimable again, and its old row stays for the history.
LIVE_STATUSES = ("held", "confirmed")

HELD = "held"
CONFIRMED = "confirmed"

# How long a tile stays yours before you have to confirm. confirm_claim refuses
# a lapsed hold; app/worker.py's sweep frees its tile.
HOLD_MINUTES = 10


class Claim(Base):
    __tablename__ = "claim"

    id: Mapped[int] = mapped_column(primary_key=True)
    # A block of tiles, half-open like range(): columns x0..x1-1, rows y0..y1-1.
    x0: Mapped[int]
    y0: Mapped[int]
    x1: Mapped[int]
    y1: Mapped[int]
    # The `sub` of a token users signed. A string, and stays one: this service
    # has no user table to make it a foreign key into, and never will.
    owner: Mapped[str]
    colour: Mapped[str]
    status: Mapped[str] = mapped_column(default=HELD)
    # A hold with no deadline is not a hold. Between the deadline and the next
    # sweep a lapsed hold still occupies its tile, but can no longer be confirmed.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # The whole point of this service. Two live blocks may not share a
        # tile: columns overlap AND rows overlap is exactly that. One row per
        # block, so overlapping requests race on one insert each and there is
        # no lock order to get wrong.
        ExcludeConstraint(
            (text("int4range(x0, x1)"), "&&"),
            (text("int4range(y0, y1)"), "&&"),
            name="no_overlapping_live_claims",
            using="gist",
            where=text("status IN ('held', 'confirmed')"),
        ),
        # The API validates bounds too. This is the copy that survives a bad
        # migration, a psql session, or a second writer that isn't this app.
        CheckConstraint(
            f"0 <= x0 AND x0 < x1 AND x1 <= {GRID_SIZE}"
            f" AND 0 <= y0 AND y0 < y1 AND y1 <= {GRID_SIZE}",
            name="block_within_canvas",
        ),
    )
