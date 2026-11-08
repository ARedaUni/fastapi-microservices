"""Stage 3: background jobs for canvas, run by arq in its own process."""

from datetime import datetime, timezone
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.redis_publisher import RedisConfig, RedisPublisher, create_client
from app.core.database import SessionLocal
from app.models.claims import HELD, Claim
from app.ports.publisher import Publisher
from app.schemas.claim import ClaimRead


async def release_expired_claims(ctx: dict[str, Any]) -> None:
    """arq entry point. arq always passes ctx first, so the session opens here."""
    async with SessionLocal() as session:
        await release_expired(session, ctx["publisher"])


async def release_expired(session: AsyncSession, publisher: Publisher) -> None:
    """Release held claims past expires_at.

    The WHERE re-checks status, so a claim confirmed in the meantime is left
    alone, and running this twice is a no-op -- arq may run a job more than once.
    """
    stmt = (
        update(Claim)
        .where(
            and_(
                Claim.status == HELD,
                Claim.expires_at < datetime.now(timezone.utc),
            )
        )
        .values(status="released")
        .returning(Claim)
    )
    released = (await session.scalars(stmt)).all()
    await session.commit()
    # After the commit, same as claim_tile: an event for a rolled-back release
    # would clear a tile that is still held.
    for claim in released:
        await publisher.publish_claim_event(ClaimRead.model_validate(claim))


async def startup(ctx: dict[str, Any]) -> None:
    ctx["publisher"] = RedisPublisher(create_client())


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["publisher"].aclose()


_redis = RedisConfig()  # type: ignore[call-arg]


class WorkerSettings:
    # A sweep, not one delayed job per claim: it reads Postgres, so a job lost
    # in Redis can't strand a hold. arq's cron lock means one firing per tick
    # however many workers run.
    cron_jobs = [cron(release_expired_claims, second={0, 30}, run_at_startup=True)]
    # users' worker drains the default arq:queue on the same Redis, and drops
    # jobs it has no function for.
    queue_name = "canvas:queue"
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(host=_redis.REDIS_HOST, port=_redis.REDIS_PORT)
