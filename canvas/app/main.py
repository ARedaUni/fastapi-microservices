from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.core.config import settings


def create_application() -> FastAPI:
    # No lifespan yet: `users/` opens an arq pool at startup, and this service
    # has no jobs to enqueue until stage 2 adds the hold-expiry worker.
    application = FastAPI(
        title=settings.PROJECT_NAME,
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
    return application


app = create_application()
