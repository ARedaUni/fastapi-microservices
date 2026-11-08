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
from tests.conftest import FakeEventBus


async def test_arq_can_run_the_job(racing_sessions: None):
    """arq calls every job as job(ctx), with real commits on its own session."""
    async with SessionLocal() as s:
        s.add(
            Claim(
                x0=1,
                y0=1,
                x1=2,
                y1=2,
                owner="ada",
                colour="#ff0055",
                status=HELD,
                expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        )
        await s.commit()

    await release_expired_claims({"publisher": FakeEventBus()})

    async with SessionLocal() as s:
        status = await s.scalar(
            select(Claim.status).where(Claim.x0 == 1, Claim.y0 == 1)
        )
    assert status == "released"


async def test_an_expired_claim_is_released(session: AsyncSession):
    """A held claim whose hold window passed is released."""
    claim = Claim(
        x0=4,
        y0=7,
        x1=5,
        y1=8,
        owner="ada",
        colour="#ff0055",
        status=HELD,
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    session.add(claim)
    await session.commit()

    await release_expired(session, FakeEventBus())

    await session.refresh(claim)
    assert claim.status == "released"


async def test_an_unexpired_claim_is_left_alone(session: AsyncSession):
    """Claims with time remaining stay held."""
    claim = Claim(
        x0=5,
        y0=8,
        x1=6,
        y1=9,
        owner="ada",
        colour="#ff0055",
        status=HELD,
        expires_at=datetime(2099, 12, 31, tzinfo=timezone.utc),
    )
    session.add(claim)
    await session.commit()

    await release_expired(session, FakeEventBus())

    await session.refresh(claim)
    assert claim.status == HELD


async def test_confirmed_claims_are_not_touched(session: AsyncSession):
    """Confirmed claims stay confirmed even if their expiry passed.

    The WHERE clause guards both status and expiry -- a claim must be held
    AND expired to be released.
    """
    claim = Claim(
        x0=6,
        y0=9,
        x1=7,
        y1=10,
        owner="ada",
        colour="#ff0055",
        status="confirmed",
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    session.add(claim)
    await session.commit()

    await release_expired(session, FakeEventBus())

    await session.refresh(claim)
    assert claim.status == "confirmed"


async def test_multiple_expired_claims_are_released(session: AsyncSession):
    """Batch update: all expired held claims are released in one query."""
    claims = [
        Claim(
            x0=i,
            y0=0,
            x1=i + 1,
            y1=1,
            owner="ada",
            colour="#ff0055",
            status=HELD,
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        for i in range(5)
    ]
    session.add_all(claims)
    await session.commit()

    await release_expired(session, FakeEventBus())

    for claim in claims:
        await session.refresh(claim)
        assert claim.status == "released"


async def test_each_released_tile_is_published(
    session: AsyncSession, fake_events: FakeEventBus
):
    """Open tabs clear a tile only if they hear it was released."""
    session.add_all(
        [
            Claim(
                x0=4,
                y0=7,
                x1=5,
                y1=8,
                owner="ada",
                colour="#ff0055",
                status=HELD,
                expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ),
            Claim(
                x0=5,
                y0=8,
                x1=6,
                y1=9,
                owner="bob",
                colour="#0055ff",
                status=HELD,
                expires_at=datetime(2099, 12, 31, tzinfo=timezone.utc),
            ),
        ]
    )
    await session.commit()

    await release_expired(session, fake_events)

    assert [(e.x0, e.y0, e.status) for e in fake_events.published] == [
        (4, 7, "released")
    ]
