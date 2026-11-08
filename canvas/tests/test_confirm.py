"""Stage 3: confirming a hold keeps the tile; a lapsed hold can't be kept."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Tuple

from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.database import SessionLocal
from app.main import app
from app.models.claims import HELD, Claim
from app.worker import release_expired
from tests.conftest import FakeEventBus, auth

CLAIMS = "/api/v1/claims/"


async def hold_a_tile(client: AsyncClient) -> int:
    res = await client.post(CLAIMS, json={"x": 4, "y": 7, "colour": "#ff0055"})
    assert res.status_code == 201, res.json()
    return int(res.json()["id"])


def confirm(claim_id: int) -> str:
    return f"{CLAIMS}{claim_id}/confirm"


async def test_the_owner_confirms_their_hold(
    client: AsyncClient, fake_events: FakeEventBus
):
    claim_id = await hold_a_tile(client)
    fake_events.published.clear()

    res = await client.post(confirm(claim_id))

    assert res.status_code == 200, res.json()
    assert res.json()["status"] == "confirmed"
    assert [e.status for e in fake_events.published] == ["confirmed"]


async def test_confirming_twice_is_a_safe_retry(
    client: AsyncClient, fake_events: FakeEventBus
):
    """A confirm whose response was lost gets retried; the retry must not fail."""
    claim_id = await hold_a_tile(client)
    await client.post(confirm(claim_id))
    fake_events.published.clear()

    res = await client.post(confirm(claim_id))

    assert res.status_code == 200
    assert res.json()["status"] == "confirmed"
    assert fake_events.published == []


async def test_someone_elses_hold_cannot_be_confirmed(client: AsyncClient):
    claim_id = await hold_a_tile(client)

    res = await client.post(confirm(claim_id), headers=auth(sub="mallory"))

    assert res.status_code == 403
    assert (await client.get(CLAIMS)).json()[0]["status"] == HELD


async def test_a_lapsed_hold_cannot_be_confirmed(
    client: AsyncClient, session: AsyncSession, fake_events: FakeEventBus
):
    """The deadline decides, not whether the sweep has got round to it yet."""
    claim_id = await hold_a_tile(client)
    claim = await session.get(Claim, claim_id)
    assert claim is not None
    claim.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    await session.commit()
    fake_events.published.clear()

    res = await client.post(confirm(claim_id))

    assert res.status_code == 409
    assert fake_events.published == []


async def test_a_released_hold_cannot_be_confirmed(
    client: AsyncClient, session: AsyncSession
):
    claim_id = await hold_a_tile(client)
    claim = await session.get(Claim, claim_id)
    assert claim is not None
    claim.status = "released"
    await session.commit()

    res = await client.post(confirm(claim_id))

    assert res.status_code == 409


async def test_an_unknown_claim_is_not_found(client: AsyncClient):
    assert (await client.post(confirm(999_999))).status_code == 404


async def test_confirming_needs_a_token(anonymous: AsyncClient):
    assert (await anonymous.post(confirm(1))).status_code == 401


async def race(
    client: AsyncClient, fake_events: FakeEventBus, sweep_first: bool
) -> Tuple[Response, str]:
    """Confirm and sweep the same hold at its deadline, in a chosen order.

    Each believes it may act: the confirm's transaction began just before the
    deadline and the sweep's just after (Postgres's now() is fixed when a
    transaction begins). A third session locks the row so both queue behind it,
    and Postgres hands them the row in the order they arrived.
    """
    async with (
        SessionLocal() as locker,
        SessionLocal() as confirming,
        SessionLocal() as sweeping,
    ):
        before_deadline = await confirming.scalar(select(func.now()))
        assert before_deadline is not None
        claim = Claim(
            x=4,
            y=7,
            owner="1",
            colour="#ff0055",
            status=HELD,
            expires_at=before_deadline + timedelta(milliseconds=1),
        )
        locker.add(claim)
        await locker.commit()
        await asyncio.sleep(0.01)
        await sweeping.scalar(select(func.now()))  # past the deadline now

        await locker.scalar(select(Claim).where(Claim.id == claim.id).with_for_update())
        app.dependency_overrides[get_session] = lambda: confirming

        async def do_confirm() -> Response:
            await asyncio.sleep(0.05 if sweep_first else 0)
            return await client.post(confirm(claim.id))

        async def do_sweep() -> None:
            await asyncio.sleep(0 if sweep_first else 0.05)
            await release_expired(sweeping, fake_events)

        pending = asyncio.gather(do_confirm(), do_sweep())
        await asyncio.sleep(0.1)  # both are now queued on the locked row
        await locker.commit()
        res, _ = await pending

        status = await locker.scalar(select(Claim.status).where(Claim.id == claim.id))
        assert status is not None
        return res, status


async def test_a_sweep_that_gets_the_row_first_wins(
    client: AsyncClient, racing_sessions: None, fake_events: FakeEventBus
):
    res, status = await race(client, fake_events, sweep_first=True)

    assert res.status_code == 409
    assert status == "released"
    assert [e.status for e in fake_events.published] == ["released"]


async def test_a_confirm_that_gets_the_row_first_wins(
    client: AsyncClient, racing_sessions: None, fake_events: FakeEventBus
):
    res, status = await race(client, fake_events, sweep_first=False)

    assert res.status_code == 200
    assert status == "confirmed"
    assert [e.status for e in fake_events.published] == ["confirmed"]
