from typing import Protocol

from app.schemas.claim import ClaimRead


class Publisher(Protocol):
    """The seam `claim_tile` calls instead of importing redis.asyncio directly.

    Kept to exactly one method, matching the one thing swapped between prod and
    tests -- see docs/second-service.md §3. `ClaimRead` is reused rather than a
    parallel event type: it already names every field worth broadcasting.
    """

    async def publish_claim_event(self, event: ClaimRead) -> None: ...
