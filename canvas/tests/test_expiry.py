"""Stage 3: expiry job tests.

Tests for the background job that releases expired holds. The core lesson:
a conditional WHERE clause makes check-and-act atomic, preventing races where
confirm and expire happen at the same microsecond.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models.claims import HELD, Claim
from app.worker import release_expired, release_expired_claims


async def test_arq_can_run_the_job(racing_sessions: None):
    """arq calls every job as job(ctx), with real commits on its own session."""
    async with SessionLocal() as s:
        s.add(
            Claim(
                x=1,
                y=1,
                owner="ada",
                colour="#ff0055",
                status=HELD,
                expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        )
        await s.commit()

    await release_expired_claims({})

    async with SessionLocal() as s:
        status = await s.scalar(select(Claim.status).where(Claim.x == 1, Claim.y == 1))
    assert status == "released"


async def test_an_expired_claim_is_released(session: AsyncSession):
    """A held claim whose hold window passed is released."""
    claim = Claim(
        x=4,
        y=7,
        owner="ada",
        colour="#ff0055",
        status=HELD,
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    session.add(claim)
    await session.commit()

    await release_expired(session)

    await session.refresh(claim)
    assert claim.status == "released"


async def test_an_unexpired_claim_is_left_alone(session: AsyncSession):
    """Claims with time remaining stay held."""
    claim = Claim(
        x=5,
        y=8,
        owner="ada",
        colour="#ff0055",
        status=HELD,
        expires_at=datetime(2099, 12, 31, tzinfo=timezone.utc),
    )
    session.add(claim)
    await session.commit()

    await release_expired(session)

    await session.refresh(claim)
    assert claim.status == HELD


async def test_confirmed_claims_are_not_touched(session: AsyncSession):
    """Confirmed claims stay confirmed even if their expiry passed.

    The WHERE clause guards both status and expiry -- a claim must be held
    AND expired to be released.
    """
    claim = Claim(
        x=6,
        y=9,
        owner="ada",
        colour="#ff0055",
        status="confirmed",
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    session.add(claim)
    await session.commit()

    await release_expired(session)

    await session.refresh(claim)
    assert claim.status == "confirmed"


async def test_multiple_expired_claims_are_released(session: AsyncSession):
    """Batch update: all expired held claims are released in one query."""
    claims = [
        Claim(
            x=i,
            y=0,
            owner="ada",
            colour="#ff0055",
            status=HELD,
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        for i in range(5)
    ]
    session.add_all(claims)
    await session.commit()

    await release_expired(session)

    for claim in claims:
        await session.refresh(claim)
        assert claim.status == "released"
