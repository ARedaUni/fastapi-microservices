from contextlib import asynccontextmanager

from arq import create_pool
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.api.jwks import router as jwks_router
from app.core import redis
from app.core.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    redis.pool = await create_pool(redis.redis_config.arq())
    yield
    # redis-py's close() is the deprecated sync shim; aclose() is the coroutine.
    await redis.pool.aclose()


def create_application() -> FastAPI:
    # Docs live under /api with everything else: the ingress forwards that one
    # prefix, so the public surface is whatever is mounted below it and nothing
    # is exposed by being left at the root.
    application = FastAPI(
        title=settings.PROJECT_NAME,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    # TODO: remove when BFF is built (stage 5). CORS at service level is temporary;
    # it moves to the BFF/ingress when the frontend has a backend entry point.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    # The one exception to the /api rule above: verifiers look for keys at
    # /.well-known/, so the ingress forwards that prefix too.
    application.include_router(jwks_router)
    return application


app = create_application()
