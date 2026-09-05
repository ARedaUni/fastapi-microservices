from typing import AsyncGenerator, Optional

import redis.asyncio as redis
from pydantic_settings import BaseSettings

from app.ports.publisher import Publisher
from app.ports.subscriber import Subscriber
from app.schemas.claim import ClaimRead

# One channel: canvas has one kind of live event today.
CLAIMS_CHANNEL = "canvas:claims"


class RedisConfig(BaseSettings):
    """The redis connection on its own, so the rest of Settings never learns
    this adapter exists -- same split as users/app/core/redis.py.
    """

    REDIS_HOST: str
    REDIS_PORT: int


class RedisPublisher(Publisher, Subscriber):
    """The only adapter behind Publisher/Subscriber today. Swapping to Streams
    or NATS for stage 8's cross-service fan-out means changing this class, not
    claim_tile or the stream endpoint -- see docs/second-service.md §3.
    """

    def __init__(self, client: "redis.Redis", channel: str = CLAIMS_CHANNEL) -> None:
        self._client = client
        self._channel = channel

    async def publish_claim_event(self, event: ClaimRead) -> None:
        await self._client.publish(self._channel, event.model_dump_json())

    async def subscribe(self) -> AsyncGenerator[str, None]:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(self._channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield message["data"]
        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()


def create_client(config: Optional[RedisConfig] = None) -> "redis.Redis":
    """One place that decides `decode_responses=True`.

    Subscriber promises `str`, and the redis-py default is bytes -- decoding
    here means neither `subscribe()` nor a test constructing its own client
    has to remember to do it.
    """
    config = config or RedisConfig()  # type: ignore[call-arg]
    return redis.Redis(
        host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
    )


# Set by app.main's lifespan and cleared at shutdown, same as users/app/core/redis.py.
_instance: Optional[RedisPublisher] = None


def connect() -> RedisPublisher:
    global _instance
    _instance = RedisPublisher(create_client())
    return _instance


async def disconnect() -> None:
    global _instance
    if _instance is not None:
        await _instance.aclose()
    _instance = None


def get_instance() -> RedisPublisher:
    """The adapter, or a clear error instead of an AttributeError on None."""
    if _instance is None:
        raise RuntimeError("redis publisher is not initialised")
    return _instance
