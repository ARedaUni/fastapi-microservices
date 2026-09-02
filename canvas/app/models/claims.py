from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# The canvas is GRID_SIZE x GRID_SIZE tiles. A constant, not a setting: nothing
# resizes a canvas people have already drawn on.
GRID_SIZE = 100

# A claim in either state owns its tile. `released` does not, which is what
# makes the unique index below partial -- a tile whose hold lapsed has to be
# claimable again, and its old row stays for the history.
LIVE_STATUSES = ("held", "confirmed")

HELD = "held"

# How long a tile stays yours before you have to confirm. Stage 2's worker
# is what enforces it; until then the deadline is recorded and ignored.
HOLD_MINUTES = 10


class Claim(Base):
    __tablename__ = "claim"

    id: Mapped[int] = mapped_column(primary_key=True)
    x: Mapped[int]
    y: Mapped[int]
    # A nickname, until stage 3. Then the token `users` signed carries a
    # user_id and this becomes that, with no user table on this side.
    owner: Mapped[str]
    colour: Mapped[str]
    status: Mapped[str] = mapped_column(default=HELD)
    # A hold with no deadline is not a hold. Stage 2's arq worker is what reads
    # this column; until it exists an expired hold still occupies its tile.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # The whole point of this service. Two requests for one tile are
        # resolved here, inside the transaction that writes the row -- not by a
        # Redis lock held outside it, which can be released by a process that
        # dies before its INSERT lands.
        Index(
            "one_live_claim_per_tile",
            "x",
            "y",
            unique=True,
            postgresql_where=text("status IN ('held', 'confirmed')"),
        ),
        # The API validates bounds too. This is the copy that survives a bad
        # migration, a psql session, or a second writer that isn't this app.
        CheckConstraint(
            f"x >= 0 AND x < {GRID_SIZE} AND y >= 0 AND y < {GRID_SIZE}",
            name="tile_within_canvas",
        ),
    )
