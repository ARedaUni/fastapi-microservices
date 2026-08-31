from contextlib import asynccontextmanager

from arq import create_pool
from fastapi import FastAPI

from app.api import router
from app.core import redis
from app.core.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    redis.pool = await create_pool(redis.redis_config.arq())
    yield
    # redis-py's close() is the deprecated sync shim; aclose() is the coroutine.
    await redis.pool.aclose()


def create_application() -> FastAPI:
    application = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
    application.include_router(router)
    return application


app = create_application()
