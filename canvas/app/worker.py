"""Stage 3: background jobs for canvas, run by arq in its own process."""

from datetime import datetime, timezone
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.redis_publisher import RedisConfig
from app.core.database import SessionLocal
from app.models.claims import HELD, Claim


async def release_expired_claims(ctx: dict[str, Any]) -> None:
    """arq entry point. arq always passes ctx first, so the session opens here."""
    async with SessionLocal() as session:
        await release_expired(session)


async def release_expired(session: AsyncSession) -> None:
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
    )
    await session.execute(stmt)
    await session.commit()


_redis = RedisConfig()  # type: ignore[call-arg]


class WorkerSettings:
    # A sweep, not one delayed job per claim: it reads Postgres, so a job lost
    # in Redis can't strand a hold. arq's cron lock means one firing per tick
    # however many workers run.
    cron_jobs = [cron(release_expired_claims, second={0, 30}, run_at_startup=True)]
    # users' worker drains the default arq:queue on the same Redis, and drops
    # jobs it has no function for.
    queue_name = "canvas:queue"
    redis_settings = RedisSettings(host=_redis.REDIS_HOST, port=_redis.REDIS_PORT)
