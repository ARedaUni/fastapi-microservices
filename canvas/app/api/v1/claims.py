from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_subject, get_publisher, get_session, get_subscriber
from app.models.claims import HELD, HOLD_MINUTES, LIVE_STATUSES, Claim
from app.ports.publisher import Publisher
from app.ports.subscriber import Subscriber
from app.schemas.claim import ClaimCreate, ClaimRead

router = APIRouter(prefix="/claims", tags=["Claims"])

ONE_LIVE_CLAIM_PER_TILE = "one_live_claim_per_tile"


@router.post("/", response_model=ClaimRead, status_code=201)
async def claim_tile(
    payload: ClaimCreate,
    owner: str = Depends(current_subject),
    session: AsyncSession = Depends(get_session),
    publisher: Publisher = Depends(get_publisher),
) -> ClaimRead:
    """Take a tile, or lose the race for it.

    No SELECT-then-INSERT. Checking first and inserting second leaves a window
    between the two where the other request wins, and no amount of retrying
    closes it. The INSERT is the check: the partial unique index decides, in
    the same transaction that writes the row, and the loser gets 409.
    """
    claim = Claim(
        **payload.model_dump(),
        owner=owner,
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
    event = ClaimRead.model_validate(claim)
    await publisher.publish_claim_event(event)
    return event


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


@router.get("/stream")
async def stream_claims(
    request: Request, subscriber: Subscriber = Depends(get_subscriber)
) -> StreamingResponse:
    """Every claim, as it happens, to whoever is watching.

    Unauthenticated, same as `list_claims`: the canvas is the public artefact,
    and this is that same read replayed live rather than polled. No
    `Last-Event-ID` replay either -- a reconnecting client re-fetches
    `GET /claims` for ground truth, then resubscribes here for the tail; see
    docs/second-service.md §3 for why that beats a second recovery mechanism.
    """

    async def event_source() -> AsyncIterator[str]:
        async for payload in subscriber.subscribe():
            if await request.is_disconnected():
                break
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
