import asyncio
import socket

from fastapi import APIRouter, Depends
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.adapters.redis_publisher import RedisPublisher
from app.adapters.redis_publisher import get_instance as get_redis_publisher
from app.api.deps import get_session

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/", status_code=204)
async def health(
    session: AsyncSession = Depends(get_session),
    redis_publisher: RedisPublisher = Depends(get_redis_publisher),
):
    try:
        await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=1)
        await asyncio.wait_for(redis_publisher.ping(), timeout=1)
    except (asyncio.TimeoutError, socket.gaierror, RedisError):
        return Response(status_code=503)
    return Response(status_code=204)
