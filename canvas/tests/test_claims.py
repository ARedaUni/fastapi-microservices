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
    """One tile, (4, 7). Corners are half-open: x1 and y1 are not included."""
    return {"x0": 4, "y0": 7, "x1": 5, "y1": 8, "colour": "#ff0055", **overrides}


def corners(claim: Dict[str, Any]) -> tuple:
    return (claim["x0"], claim["y0"], claim["x1"], claim["y1"])


async def test_claiming_a_free_tile_holds_it(client: AsyncClient):
    res = await client.post(CLAIMS, json=a_claim())

    assert res.status_code == 201, res.json()
    body = res.json()
    assert corners(body) == (4, 7, 5, 8)
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
    assert (event.x0, event.y0, event.x1, event.y1) == (4, 7, 5, 8)
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

    res = await client.post(CLAIMS, json=a_claim(x0=5, x1=6))

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
    await client.post(CLAIMS, json=a_claim(x0=9, y0=9, x1=10, y1=10))
    lapsed = await session.get(Claim, held.json()["id"])
    assert lapsed is not None
    lapsed.status = "released"
    await session.commit()

    res = await client.get(CLAIMS)

    assert res.status_code == 200
    assert [corners(c) for c in res.json()] == [(9, 9, 10, 10)]


async def test_a_tile_off_the_grid_is_rejected(client: AsyncClient):
    for off_grid in (a_claim(x1=101), a_claim(y0=-1)):
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
            x0=500,
            y0=0,
            x1=501,
            y1=1,
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
        raised = "block_within_canvas" in str(exc.orig)
        await session.rollback()

    assert raised


async def test_holding_a_block_holds_every_tile_in_it(client: AsyncClient):
    res = await client.post(CLAIMS, json=a_claim(x0=3, y0=3, x1=8, y1=5))

    assert res.status_code == 201, res.json()
    assert corners(res.json()) == (3, 3, 8, 5)


async def test_a_block_overlapping_a_live_one_is_rejected_whole(
    client: AsyncClient,
):
    """One shared tile is enough, and the loser gets none of the others."""
    await client.post(CLAIMS, json=a_claim(x0=0, y0=0, x1=5, y1=5))

    res = await client.post(CLAIMS, json=a_claim(x0=4, y0=4, x1=8, y1=8))

    assert res.status_code == 409
    assert "(0, 0)" in res.json()["detail"]  # names the block in the way
    assert len((await client.get(CLAIMS)).json()) == 1


async def test_blocks_whose_edges_touch_do_not_overlap(client: AsyncClient):
    """Half-open: x1=5 means up to column 4, so the next block starts at 5."""
    await client.post(CLAIMS, json=a_claim(x0=0, y0=0, x1=5, y1=5))

    beside = await client.post(CLAIMS, json=a_claim(x0=5, y0=0, x1=8, y1=3))
    below = await client.post(CLAIMS, json=a_claim(x0=0, y0=5, x1=5, y1=8))

    assert (beside.status_code, below.status_code) == (201, 201)


async def test_a_block_overlapping_on_one_axis_only_is_fine(client: AsyncClient):
    """Same columns, different rows: stacked, not overlapping."""
    await client.post(CLAIMS, json=a_claim(x0=0, y0=0, x1=5, y1=5))

    res = await client.post(CLAIMS, json=a_claim(x0=2, y0=6, x1=4, y1=8))

    assert res.status_code == 201


async def test_an_empty_or_inside_out_block_is_rejected(client: AsyncClient):
    for bad in (a_claim(x1=4), a_claim(y1=6)):
        res = await client.post(CLAIMS, json=bad)
        assert res.status_code == 422, bad


async def test_two_concurrent_overlapping_blocks_leave_one_winner(
    client: AsyncClient, racing_sessions: None
):
    """Alice and Bob from the deadlock lesson: one row each, so nothing to order."""
    alice, bob = await asyncio.gather(
        client.post(
            CLAIMS, json=a_claim(x0=0, y0=0, x1=5, y1=5), headers=auth(sub="alice")
        ),
        client.post(
            CLAIMS, json=a_claim(x0=3, y0=3, x1=8, y1=8), headers=auth(sub="bob")
        ),
    )

    assert sorted([alice.status_code, bob.status_code]) == [201, 409]
    assert len((await client.get(CLAIMS)).json()) == 1


async def test_health_reports_the_database(client: AsyncClient, session: AsyncSession):
    assert (await client.get("/api/health/")).status_code == 204
    assert (await session.execute(select(Claim))).scalars().all() == []
