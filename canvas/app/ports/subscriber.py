from typing import AsyncIterator, Protocol


class Subscriber(Protocol):
    """The seam the SSE endpoint reads through instead of importing redis.asyncio.

    Returns raw JSON strings, not `ClaimRead`: the subscriber only relays what
    the publisher already serialised, so decoding and re-encoding it here would
    buy nothing.
    """

    def subscribe(self) -> AsyncIterator[str]: ...
