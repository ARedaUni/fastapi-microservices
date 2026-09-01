from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.claims import HELD, HOLD_MINUTES, LIVE_STATUSES, Claim
from app.schemas.claim import ClaimCreate, ClaimRead

router = APIRouter(prefix="/claims", tags=["Claims"])

ONE_LIVE_CLAIM_PER_TILE = "one_live_claim_per_tile"


@router.post("/", response_model=ClaimRead, status_code=201)
async def claim_tile(
    payload: ClaimCreate, session: AsyncSession = Depends(get_session)
) -> Claim:
    """Take a tile, or lose the race for it.

    No SELECT-then-INSERT. Checking first and inserting second leaves a window
    between the two where the other request wins, and no amount of retrying
    closes it. The INSERT is the check: the partial unique index decides, in
    the same transaction that writes the row, and the loser gets 409.
    """
    claim = Claim(
        **payload.model_dump(),
        status=HELD,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=HOLD_MINUTES),
    )
    session.add(claim)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # Matched by name so a future constraint -- the bounds CHECK, say --
        # surfaces as a 500 we go and look at, rather than hiding behind a 409
        # that tells the caller to try a different tile.
        # ponytail: string match on the driver's message; asyncpg exposes the
        # constraint name only through the wrapped DBAPI error. Switch to
        # exc.orig.constraint_name if that ever becomes reachable.
        if ONE_LIVE_CLAIM_PER_TILE not in str(exc.orig):
            raise
        raise HTTPException(
            status_code=409,
            detail=f"Tile ({payload.x}, {payload.y}) is already claimed",
        )
    return claim


@router.get("/", response_model=List[ClaimRead])
async def list_claims(session: AsyncSession = Depends(get_session)):
    """The canvas as it stands: every tile someone currently owns.

    Unpaginated on purpose -- the grid is bounded, so this cannot return more
    than GRID_SIZE squared rows however popular the canvas gets.
    """
    result = await session.execute(
        select(Claim).where(Claim.status.in_(LIVE_STATUSES)).order_by(Claim.y, Claim.x)
    )
    return result.scalars().all()
