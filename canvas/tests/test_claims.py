import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claims import HELD, Claim
from tests.conftest import FakeEventBus, auth

CLAIMS = "/api/v1/claims/"


def a_claim(**overrides: Any) -> Dict[str, Any]:
    return {"x": 4, "y": 7, "colour": "#ff0055", **overrides}


async def test_claiming_a_free_tile_holds_it(client: AsyncClient):
    res = await client.post(CLAIMS, json=a_claim())

    assert res.status_code == 201, res.json()
    body = res.json()
    assert (body["x"], body["y"]) == (4, 7)
    assert body["status"] == HELD
    assert datetime.fromisoformat(body["expires_at"]) > datetime.now(timezone.utc)


async def test_claiming_a_tile_publishes_a_claim_event(
    client: AsyncClient, fake_events: FakeEventBus
):
    """Stage 2: everyone else has to see this happen without asking."""
    res = await client.post(CLAIMS, json=a_claim())

    assert res.status_code == 201
    assert len(fake_events.published) == 1
    event = fake_events.published[0]
    assert (event.x, event.y) == (4, 7)
    assert event.status == HELD


async def test_a_rejected_claim_publishes_no_event(
    client: AsyncClient, fake_events: FakeEventBus
):
    """The loser of a race changed nothing, so nobody should hear about it."""
    await client.post(CLAIMS, json=a_claim())
    fake_events.published.clear()

    res = await client.post(CLAIMS, json=a_claim(colour="#00ff00"))

    assert res.status_code == 409
    assert fake_events.published == []


async def test_claiming_a_taken_tile_is_rejected(client: AsyncClient):
    assert (await client.post(CLAIMS, json=a_claim())).status_code == 201

    res = await client.post(CLAIMS, json=a_claim(colour="#00ff00"))

    assert res.status_code == 409
    assert "(4, 7)" in res.json()["detail"]


async def test_a_neighbouring_tile_is_unaffected(client: AsyncClient):
    assert (await client.post(CLAIMS, json=a_claim())).status_code == 201

    res = await client.post(CLAIMS, json=a_claim(x=5))

    assert res.status_code == 201


async def test_a_released_claim_frees_its_tile(
    client: AsyncClient, session: AsyncSession
):
    """The index is partial, and this is the half that proves it.

    A tile whose hold lapsed has to be claimable again while its old row stays
    for the history. A plain unique index would refuse the second claim here.
    """
    first = await client.post(CLAIMS, json=a_claim())
    claim = await session.get(Claim, first.json()["id"])
    assert claim is not None
    claim.status = "released"
    await session.commit()

    res = await client.post(CLAIMS, json=a_claim())

    assert res.status_code == 201


async def test_two_concurrent_claims_for_one_tile_leave_one_winner(
    client: AsyncClient, racing_sessions: None
):
    """The reason this service exists.

    Two requests, one tile, separate connections. Postgres decides inside the
    transaction that writes the row, so exactly one 201 is possible -- and one
    row survives, not two.
    """
    first, second = await asyncio.gather(
        client.post(CLAIMS, json=a_claim(), headers=auth(sub="ada")),
        client.post(CLAIMS, json=a_claim(colour="#00ff00"), headers=auth(sub="grace")),
    )

    assert sorted([first.status_code, second.status_code]) == [201, 409]

    listed = await client.get(CLAIMS)
    assert len(listed.json()) == 1


async def test_the_canvas_lists_live_claims_only(
    client: AsyncClient, session: AsyncSession
):
    held = await client.post(CLAIMS, json=a_claim())
    await client.post(CLAIMS, json=a_claim(x=9, y=9))
    lapsed = await session.get(Claim, held.json()["id"])
    assert lapsed is not None
    lapsed.status = "released"
    await session.commit()

    res = await client.get(CLAIMS)

    assert res.status_code == 200
    assert [(c["x"], c["y"]) for c in res.json()] == [(9, 9)]


async def test_a_tile_off_the_grid_is_rejected(client: AsyncClient):
    for off_grid in (a_claim(x=100), a_claim(y=-1)):
        res = await client.post(CLAIMS, json=off_grid)
        assert res.status_code == 422, off_grid


async def test_a_colour_that_is_not_a_hex_triplet_is_rejected(client: AsyncClient):
    for bad in ("red", "#fff", "#gggggg", "#ff0055; DROP TABLE claim"):
        res = await client.post(CLAIMS, json=a_claim(colour=bad))
        assert res.status_code == 422, bad


async def test_the_check_constraint_backs_up_the_api(session: AsyncSession):
    """Bounds live in two places, and this is the one the API cannot bypass."""
    from sqlalchemy.exc import IntegrityError

    session.add(
        Claim(
            x=500,
            y=0,
            owner="ada",
            colour="#ff0055",
            status=HELD,
            expires_at=datetime.now(timezone.utc),
        )
    )
    try:
        await session.commit()
        raised = False
    except IntegrityError as exc:
        raised = "tile_within_canvas" in str(exc.orig)
        await session.rollback()

    assert raised


async def test_health_reports_the_database(client: AsyncClient, session: AsyncSession):
    assert (await client.get("/api/health/")).status_code == 204
    assert (await session.execute(select(Claim))).scalars().all() == []
