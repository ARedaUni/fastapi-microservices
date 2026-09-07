import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator, List

import pytest
import redis.asyncio as redis
from httpx import AsyncClient

from app.adapters.redis_publisher import RedisPublisher, create_client
from app.api.deps import get_subscriber
from app.main import app
from app.schemas.claim import ClaimRead

STREAM = "/api/v1/claims/stream"


class _FiniteSubscriber:
    """A subscriber that ends, standing in for a client that disconnects.

    A real subscribe() never returns on its own; framing the SSE output is
    tested here without needing a disconnect to prove it.
    """

    def __init__(self, payloads: List[str]) -> None:
        self._payloads = payloads

    async def subscribe(self) -> AsyncIterator[str]:
        for payload in self._payloads:
            yield payload


async def test_stream_relays_events_as_sse_frames(anonymous: AsyncClient):
    payloads = [json.dumps({"x": 1, "y": 2}), json.dumps({"x": 3, "y": 4})]
    app.dependency_overrides[get_subscriber] = lambda: _FiniteSubscriber(payloads)

    res = await anonymous.get(STREAM)

    assert res.headers["content-type"].startswith("text/event-stream")
    assert res.text == "".join(f"data: {p}\n\n" for p in payloads)


async def test_the_stream_needs_no_token(anonymous: AsyncClient):
    """Same rule as list_claims: the canvas is the public artefact."""
    app.dependency_overrides[get_subscriber] = lambda: _FiniteSubscriber([])

    assert (await anonymous.get(STREAM)).status_code == 200


@pytest.fixture()
async def redis_client() -> AsyncIterator["redis.Redis"]:
    client = create_client()  # real REDIS_HOST/PORT from the env
    yield client
    await client.aclose()


async def test_redis_publisher_delivers_to_a_real_subscriber(
    redis_client: "redis.Redis",
):
    """The one seam that's real, not faked -- proves the adapter itself, not
    just that claim_tile calls the port it was handed. Every other test in
    this service substitutes FakeEventBus; this is the one that would catch a
    mistake in how RedisPublisher actually talks to Redis.
    """
    publisher = RedisPublisher(redis_client, channel="canvas-test:claims")
    event = ClaimRead(
        id=1,
        x=1,
        y=1,
        owner="ada",
        colour="#ff0000",
        status="held",
        expires_at=datetime.now(timezone.utc),
    )
    messages = publisher.subscribe()

    async def publish_until_seen() -> None:
        # subscribe() only registers with Redis once it is first iterated, and
        # that SUBSCRIBE is a real network round trip -- so the first publish
        # can legitimately race ahead of it. Retry rather than guess a sleep.
        for _ in range(50):
            await publisher.publish_claim_event(event)
            await asyncio.sleep(0.05)

    publishing = asyncio.create_task(publish_until_seen())
    try:
        received = await asyncio.wait_for(messages.__anext__(), timeout=3)
    finally:
        publishing.cancel()
        await messages.aclose()

    assert received == event.model_dump_json()
